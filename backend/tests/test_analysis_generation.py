"""Tests de la génération de l'analyse de dossier pendant l'exécution (issue #125).

Le pipeline existant (worker -> API interne) est inchangé ; l'analyse de
dossier s'en déduit : une analyse par lancement, des unités déclarées par le
worker, un élément par prédiction déposée dans une unité, une synthèse par
agent terminé."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

INTERNAL = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


@pytest.fixture(autouse=True)
def _no_celery_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un lancement ne doit pas déposer de vraies tâches dans la file partagée."""
    for name in ("dispatch_classification", "dispatch_entity_extraction", "dispatch_agent_execution"):
        monkeypatch.setattr(f"app.routers.dossiers.{name}", lambda dossier_id, *args, **kwargs: None)


def _create_dossier(client: TestClient, *, agent: str | None = None) -> str:
    analyse_id = client.post("/api/analyses", json={"name": "Analyse génération", "description": "Test"}).json()["id"]
    if agent:
        client.post(
            f"/api/analyses/{analyse_id}/agents",
            json={"name": agent, "prompt": "Vérifie.", "tools": [], "output": True},
        )
    return client.post("/api/dossiers", json={"name": "Dossier génération", "analyse_id": analyse_id}).json()["id"]


def _launch(client: TestClient, dossier_id: str) -> dict[str, Any]:
    return client.post(f"/api/dossiers/{dossier_id}/launch").json()


def _current(client: TestClient, dossier_id: str) -> dict[str, Any]:
    return client.get(f"/api/dossiers/{dossier_id}/analyse-dossier").json()


def _page(client: TestClient, dossier_id: str) -> dict[str, Any]:
    document = client.post(
        f"/api/dossiers/{dossier_id}/documents",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
    ).json()["documents"][0]
    return client.post(
        f"/api/internal/documents/{document['id']}/pages",
        json={"page_number": 3, "content": "texte"},
        headers=INTERNAL,
    ).json()


def _unit(client: TestClient, dossier_id: str, kind: str = "classification", **description: Any) -> dict[str, Any]:
    response = client.post(
        f"/api/internal/dossiers/{dossier_id}/analysis-units",
        json={"kind": kind, "description": description},
        headers=INTERNAL,
    )
    assert response.status_code == 201
    return response.json()


def _predict(client: TestClient, page_id: str, **fields: Any) -> dict[str, Any]:
    body = {"kind": "label", "name": "CNI", "value": "CNI", "confidence": 0.9, **fields}
    response = client.post(f"/api/internal/pages/{page_id}/predictions", json=body, headers=INTERNAL)
    assert response.status_code == 201
    return response.json()


# --- Une analyse par lancement ---


def test_launch_creates_the_analysis_of_the_execution(client: TestClient) -> None:
    dossier_id = _create_dossier(client)
    assert client.get(f"/api/dossiers/{dossier_id}/analyse-dossier").status_code == 404

    _launch(client, dossier_id)
    analysis = _current(client, dossier_id)
    assert analysis["sequence"] == 1
    assert analysis["status"] == "brouillon"
    assert analysis["analyse_version"] == "v1"
    assert analysis["started_at"] is not None
    assert analysis["elements"] == []


def test_launching_a_running_dossier_does_not_create_another_analysis(client: TestClient) -> None:
    dossier_id = _create_dossier(client)
    _launch(client, dossier_id)
    _launch(client, dossier_id)
    assert len(client.get(f"/api/dossiers/{dossier_id}/analyses-dossier").json()) == 1


def test_relaunch_after_stop_creates_a_new_analysis(client: TestClient) -> None:
    dossier_id = _create_dossier(client)
    _launch(client, dossier_id)
    client.post(f"/api/dossiers/{dossier_id}/stop")
    _launch(client, dossier_id)

    analyses = client.get(f"/api/dossiers/{dossier_id}/analyses-dossier").json()
    assert [a["sequence"] for a in analyses] == [2, 1]
    assert _current(client, dossier_id)["sequence"] == 2


# --- Unités déclarées par le worker ---


def test_worker_declares_and_completes_a_unit(client: TestClient) -> None:
    dossier_id = _create_dossier(client)
    _launch(client, dossier_id)
    unit = _unit(client, dossier_id, "extraction", page_numbers=[1, 2, 3])
    analysis_id = _current(client, dossier_id)["id"]
    assert unit["analysis_id"] == analysis_id

    units = client.get(f"/api/dossiers/{dossier_id}/analyses-dossier/{analysis_id}/units").json()
    assert [(u["kind"], u["status"], u["description"]) for u in units] == [
        ("extraction", "en_cours", {"page_numbers": [1, 2, 3]})
    ]

    done = client.post(
        f"/api/internal/analysis-units/{unit['id']}/complete", json={"status": "terminé"}, headers=INTERNAL
    )
    assert done.status_code == 200
    units = client.get(f"/api/dossiers/{dossier_id}/analyses-dossier/{analysis_id}/units").json()
    assert units[0]["status"] == "terminé"

    client.post(f"/api/internal/analysis-units/{unit['id']}/complete", json={"status": "échec"}, headers=INTERNAL)
    units = client.get(f"/api/dossiers/{dossier_id}/analyses-dossier/{analysis_id}/units").json()
    assert units[0]["status"] == "échec"


def test_unit_of_a_dossier_without_analysis_is_404(client: TestClient) -> None:
    dossier_id = _create_dossier(client)  # jamais lancé : pas d'analyse
    response = client.post(
        f"/api/internal/dossiers/{dossier_id}/analysis-units", json={"kind": "classification"}, headers=INTERNAL
    )
    assert response.status_code == 404


def test_unit_routes_require_a_valid_app_token(client: TestClient) -> None:
    dossier_id = _create_dossier(client)
    _launch(client, dossier_id)
    unit = _unit(client, dossier_id)
    bad = {"X-App-Token": "not-a-valid-token"}
    create = client.post(f"/api/internal/dossiers/{dossier_id}/analysis-units", json={"kind": "agent"}, headers=bad)
    complete = client.post(
        f"/api/internal/analysis-units/{unit['id']}/complete", json={"status": "terminé"}, headers=bad
    )
    assert (create.status_code, complete.status_code) == (401, 401)


def test_complete_unknown_unit_is_404(client: TestClient) -> None:
    response = client.post(
        f"/api/internal/analysis-units/{uuid.uuid4()}/complete", json={"status": "terminé"}, headers=INTERNAL
    )
    assert response.status_code == 404


# --- Prédiction -> élément ---


def test_prediction_in_a_unit_becomes_an_element(client: TestClient) -> None:
    dossier_id = _create_dossier(client)
    _launch(client, dossier_id)
    page = _page(client, dossier_id)
    unit = _unit(client, dossier_id)

    prediction = _predict(client, page["id"], unit_id=unit["id"])

    analysis = _current(client, dossier_id)
    [element] = analysis["elements"]
    assert element["kind"] == "classification"
    assert element["unit_id"] == unit["id"]
    assert element["definition_name"] == "CNI"
    assert element["source_prediction_id"] == prediction["id"]
    assert element["first_page_number"] == 3
    assert element["document_id"]
    version = element["retained_version"]
    assert version["value"] == {"label": "CNI"}
    assert version["origin"] == "model"
    assert version["confidence"] == 0.9
    assert version["prediction_id"] == prediction["id"]
    assert element["latest_model_version"]["id"] == version["id"]

    units = client.get(f"/api/dossiers/{dossier_id}/analyses-dossier/{analysis['id']}/units").json()
    assert units[0]["element_count"] == 1


def test_entity_prediction_becomes_an_entity_element(client: TestClient) -> None:
    dossier_id = _create_dossier(client)
    _launch(client, dossier_id)
    page = _page(client, dossier_id)
    unit = _unit(client, dossier_id, "extraction")

    _predict(client, page["id"], kind="entity", name="nom", value="Dupont", unit_id=unit["id"])

    [element] = _current(client, dossier_id)["elements"]
    assert element["kind"] == "entity"
    assert element["definition_name"] == "nom"
    assert element["retained_version"]["value"] == {"value": "Dupont"}


def test_prediction_without_unit_is_deposited_as_before(client: TestClient) -> None:
    dossier_id = _create_dossier(client)
    _launch(client, dossier_id)
    page = _page(client, dossier_id)

    prediction = _predict(client, page["id"])

    assert prediction["name"] == "CNI"
    assert _current(client, dossier_id)["elements"] == []


def test_prediction_with_unknown_unit_is_404_and_stores_nothing(client: TestClient) -> None:
    dossier_id = _create_dossier(client)
    _launch(client, dossier_id)
    page = _page(client, dossier_id)
    response = client.post(
        f"/api/internal/pages/{page['id']}/predictions",
        json={"kind": "label", "name": "CNI", "value": "CNI", "unit_id": str(uuid.uuid4())},
        headers=INTERNAL,
    )
    assert response.status_code == 404
    document_id = client.get(f"/api/dossiers/{dossier_id}").json()["documents"][0]["id"]
    pages = client.get(f"/api/internal/documents/{document_id}", headers=INTERNAL).json()["pages"]
    assert pages[0]["predictions"] == []


def test_element_creation_is_idempotent_per_prediction(client: TestClient) -> None:
    from app.db import async_session_factory
    from app.models.document_page import DocumentPage, DocumentPrediction
    from app.repositories.dossier_analysis_repository import DossierAnalysisRepository
    from app.services import analysis_builder

    dossier_id = _create_dossier(client)
    _launch(client, dossier_id)
    page = _page(client, dossier_id)
    unit = _unit(client, dossier_id)
    prediction = _predict(client, page["id"], unit_id=unit["id"])

    async def replay() -> None:
        async with async_session_factory() as session:
            repository = DossierAnalysisRepository(session)
            await analysis_builder._create_element_from_prediction(
                repository,
                await repository.get_unit(uuid.UUID(unit["id"])),
                await session.get(DocumentPrediction, uuid.UUID(prediction["id"])),
                await session.get(DocumentPage, uuid.UUID(page["id"])),
            )

    client.portal.call(replay)
    analysis = _current(client, dossier_id)
    assert len(analysis["elements"]) == 1
    units = client.get(f"/api/dossiers/{dossier_id}/analyses-dossier/{analysis['id']}/units").json()
    assert units[0]["element_count"] == 1


# --- Fin d'étape : agents et échecs ---


def _step(client: TestClient, dossier: dict[str, Any], kind: str) -> dict[str, Any]:
    return next(s for s in dossier["execution_steps"] if s["kind"] == kind)


def test_finished_agent_gives_a_unit_and_a_synthesis(client: TestClient) -> None:
    dossier_id = _create_dossier(client, agent="Cohérence")
    dossier = _launch(client, dossier_id)
    step = _step(client, dossier, "agent")

    client.post(
        f"/api/internal/execution-steps/{step['id']}/complete",
        json={"status": "terminé", "output": "Les pièces sont cohérentes."},
        headers=INTERNAL,
    )

    analysis = _current(client, dossier_id)
    [element] = analysis["elements"]
    assert element["kind"] == "synthesis"
    assert element["definition_name"] == "Cohérence"
    assert element["retained_version"]["value"] == {"text": "Les pièces sont cohérentes."}
    assert element["retained_version"]["origin"] == "model"
    units = client.get(f"/api/dossiers/{dossier_id}/analyses-dossier/{analysis['id']}/units").json()
    [unit] = [u for u in units if u["kind"] == "agent"]
    assert unit["status"] == "terminé"
    assert unit["description"]["step_id"] == step["id"]
    assert unit["element_count"] == 1


def test_completing_an_agent_twice_does_not_duplicate_the_synthesis(client: TestClient) -> None:
    dossier_id = _create_dossier(client, agent="Cohérence")
    step = _step(client, _launch(client, dossier_id), "agent")
    for _ in range(2):
        client.post(
            f"/api/internal/execution-steps/{step['id']}/complete",
            json={"status": "terminé", "output": "OK"},
            headers=INTERNAL,
        )
    assert len(_current(client, dossier_id)["elements"]) == 1


def test_failed_agent_gives_a_failed_unit_and_no_element(client: TestClient) -> None:
    dossier_id = _create_dossier(client, agent="Cohérence")
    step = _step(client, _launch(client, dossier_id), "agent")
    client.post(
        f"/api/internal/execution-steps/{step['id']}/complete",
        json={"status": "échec", "output": "boom"},
        headers=INTERNAL,
    )
    analysis = _current(client, dossier_id)
    assert analysis["elements"] == []
    units = client.get(f"/api/dossiers/{dossier_id}/analyses-dossier/{analysis['id']}/units").json()
    assert [(u["kind"], u["status"]) for u in units] == [("agent", "échec")]


def test_failed_extraction_step_closes_its_open_units(client: TestClient) -> None:
    dossier_id = _create_dossier(client)
    dossier = _launch(client, dossier_id)
    unfinished = _unit(client, dossier_id, "extraction", page_numbers=[1])
    finished = _unit(client, dossier_id, "extraction", page_numbers=[2])
    client.post(f"/api/internal/analysis-units/{finished['id']}/complete", json={"status": "terminé"}, headers=INTERNAL)
    other_kind = _unit(client, dossier_id, "classification")

    client.post(
        f"/api/internal/execution-steps/{_step(client, dossier, 'extraction')['id']}/complete",
        json={"status": "échec", "output": "LLM indisponible"},
        headers=INTERNAL,
    )

    analysis_id = _current(client, dossier_id)["id"]
    units = {u["id"]: u for u in client.get(f"/api/dossiers/{dossier_id}/analyses-dossier/{analysis_id}/units").json()}
    assert units[unfinished["id"]]["status"] == "échec"
    assert units[finished["id"]]["status"] == "terminé"
    # Les unités d'une autre étape ne sont pas touchées.
    assert units[other_kind["id"]]["status"] == "en_cours"


def test_step_completes_for_a_dossier_without_analysis(client: TestClient) -> None:
    """Dossier dont l'exécution a démarré avant #125 : aucune analyse, l'étape
    se termine normalement."""
    dossier_id = _create_dossier(client, agent="Cohérence")
    step = _step(client, _launch(client, dossier_id), "agent")

    async def drop_analyses() -> None:
        from sqlalchemy import delete

        from app.db import async_session_factory
        from app.models.dossier_analysis import DossierAnalysis

        async with async_session_factory() as session:
            await session.execute(delete(DossierAnalysis).where(DossierAnalysis.dossier_id == uuid.UUID(dossier_id)))
            await session.commit()

    client.portal.call(drop_analyses)
    response = client.post(
        f"/api/internal/execution-steps/{step['id']}/complete",
        json={"status": "terminé", "output": "OK"},
        headers=INTERNAL,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "terminé"
    assert client.get(f"/api/dossiers/{dossier_id}/analyse-dossier").status_code == 404


# --- Empreintes d'entrées des unités (issue #126) ---

FP_A = "a" * 64
FP_B = "b" * 64


def _unit_with_fingerprint(
    client: TestClient, dossier_id: str, fingerprint: str | None, kind: str = "extraction"
) -> dict:
    body: dict[str, Any] = {"kind": kind, "description": {}}
    if fingerprint is not None:
        body["input_fingerprint"] = fingerprint
    response = client.post(f"/api/internal/dossiers/{dossier_id}/analysis-units", json=body, headers=INTERNAL)
    assert response.status_code == 201
    return response.json()


def _units(client: TestClient, dossier_id: str) -> list[dict[str, Any]]:
    analysis_id = _current(client, dossier_id)["id"]
    return client.get(f"/api/dossiers/{dossier_id}/analyses-dossier/{analysis_id}/units").json()


def test_worker_unit_keeps_its_input_fingerprint(client: TestClient) -> None:
    dossier_id = _create_dossier(client)
    _launch(client, dossier_id)
    _unit_with_fingerprint(client, dossier_id, FP_A)
    _unit_with_fingerprint(client, dossier_id, None, "classification")

    units = {u["kind"]: u for u in _units(client, dossier_id)}
    assert units["extraction"]["input_fingerprint"] == FP_A
    assert units["classification"]["input_fingerprint"] is None


@pytest.mark.parametrize("bad", ["abc", "g" * 64, "A" * 64, "a" * 65])
def test_malformed_fingerprint_is_refused(client: TestClient, bad: str) -> None:
    dossier_id = _create_dossier(client)
    _launch(client, dossier_id)
    response = client.post(
        f"/api/internal/dossiers/{dossier_id}/analysis-units",
        json={"kind": "extraction", "input_fingerprint": bad},
        headers=INTERNAL,
    )
    assert response.status_code == 422


def _agent_id(client: TestClient, analyse_id: str) -> str:
    return client.get(f"/api/analyses/{analyse_id}").json()["agents"][0]["id"]


def _finish_agent(client: TestClient, dossier_id: str, upstream: list[str], *, prompt: str | None = None) -> str | None:
    """Lance le dossier, déclare des unités amont, termine l'agent et renvoie
    l'empreinte de son unité."""
    dossier = _launch(client, dossier_id)
    for fingerprint in upstream:
        _unit_with_fingerprint(client, dossier_id, fingerprint)
    step = _step(client, dossier, "agent")
    client.post(
        f"/api/internal/execution-steps/{step['id']}/complete",
        json={"status": "terminé", "output": "OK"},
        headers=INTERNAL,
    )
    [agent_unit] = [u for u in _units(client, dossier_id) if u["kind"] == "agent"]
    return agent_unit["input_fingerprint"]


def test_agent_unit_fingerprint_depends_on_its_configuration_and_on_what_it_reads(client: TestClient) -> None:
    def fingerprint_for(upstream: list[str], prompt: str) -> str | None:
        dossier_id = _create_dossier(client, agent="Cohérence")
        dossier = client.get(f"/api/dossiers/{dossier_id}").json()
        agent_id = _agent_id(client, dossier["analyse_id"])
        client.put(f"/api/analyses/{dossier['analyse_id']}/agents/{agent_id}/prompt", json={"prompt": prompt})
        return _finish_agent(client, dossier_id, upstream)

    base = fingerprint_for([FP_A], "Vérifie la cohérence.")
    assert base and len(base) == 64
    assert fingerprint_for([FP_A], "Vérifie la cohérence.") == base
    # L'ordre des unités amont n'a pas d'importance.
    assert fingerprint_for([FP_B, FP_A], "Vérifie la cohérence.") != base  # une unité de plus
    assert fingerprint_for([FP_A], "Vérifie autre chose.") != base  # prompt modifié
    assert fingerprint_for([FP_B], "Vérifie la cohérence.") != base  # ce qu'il lit a changé
    two_a = fingerprint_for([FP_A, FP_B], "Vérifie la cohérence.")
    two_b = fingerprint_for([FP_B, FP_A], "Vérifie la cohérence.")
    assert two_a == two_b


def test_failed_agent_also_gets_a_fingerprint(client: TestClient) -> None:
    dossier_id = _create_dossier(client, agent="Cohérence")
    step = _step(client, _launch(client, dossier_id), "agent")
    client.post(
        f"/api/internal/execution-steps/{step['id']}/complete",
        json={"status": "échec", "output": "boom"},
        headers=INTERNAL,
    )
    [agent_unit] = [u for u in _units(client, dossier_id) if u["kind"] == "agent"]
    assert agent_unit["status"] == "échec"
    assert agent_unit["input_fingerprint"] and len(agent_unit["input_fingerprint"]) == 64
