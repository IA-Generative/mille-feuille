"""Tests de la relance incrémentale de l'analyse de dossier (issue #119).

Relancer un dossier crée une nouvelle analyse qui reprend les unités dont
l'empreinte est inchangée (éléments et versions copiés, aucun appel au LLM), et
conserve les valeurs validées par un instructeur des unités recalculées, « à
revoir ». Il n'y a aucun appariement : seules les empreintes comptent."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db import async_session_factory
from app.models.dossier_analysis import AnalysisElement

INTERNAL = {"X-App-Token": "dev-only-worker-token-not-for-prod"}
FP_CLS_1 = "1" * 64
FP_CLS_2 = "2" * 64
FP_EXT = "3" * 64
FP_EXT_CHANGED = "4" * 64


@pytest.fixture(autouse=True)
def _no_celery_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("dispatch_classification", "dispatch_entity_extraction", "dispatch_agent_execution"):
        monkeypatch.setattr(f"app.routers.dossiers.{name}", lambda dossier_id, *args, **kwargs: None)


class Dossier:
    """Un dossier de test : un document de 2 pages, rejouable."""

    def __init__(self, client: TestClient, *, agent: str | None = None) -> None:
        self.client = client
        analyse_id = client.post("/api/analyses", json={"name": "Analyse relance", "description": "t"}).json()["id"]
        self.analyse_id = analyse_id
        if agent:
            client.post(
                f"/api/analyses/{analyse_id}/agents",
                json={"name": agent, "prompt": "Vérifie.", "tools": [], "output": True},
            )
        self.id = client.post("/api/dossiers", json={"name": "Dossier relance", "analyse_id": analyse_id}).json()["id"]
        document = client.post(
            f"/api/dossiers/{self.id}/documents", files=[("files", ("a.pdf", b"x", "application/pdf"))]
        ).json()["documents"][0]
        self.document_id = document["id"]
        self.pages = [
            client.post(
                f"/api/internal/documents/{self.document_id}/pages",
                json={"page_number": n, "content": f"page {n}"},
                headers=INTERNAL,
            ).json()
            for n in (1, 2)
        ]
        self.steps: dict[str, dict[str, Any]] = {}

    # --- Lancement ---

    def launch(self) -> None:
        dossier = self.client.post(f"/api/dossiers/{self.id}/launch").json()
        self.steps = {s["kind"]: s for s in dossier["execution_steps"]}

    def stop_and_launch(self) -> None:
        self.client.post(f"/api/dossiers/{self.id}/stop")
        self.launch()

    # --- Ce que fait le worker ---

    def unit(self, kind: str, fingerprint: str | None, **description: Any) -> dict[str, Any]:
        body: dict[str, Any] = {"kind": kind, "description": description}
        if fingerprint:
            body["input_fingerprint"] = fingerprint
        response = self.client.post(f"/api/internal/dossiers/{self.id}/analysis-units", json=body, headers=INTERNAL)
        assert response.status_code == 201
        return response.json()

    def predict(self, page: dict[str, Any], unit_id: str, **fields: Any) -> dict[str, Any]:
        body = {"kind": "entity", "name": "nom", "value": "Dupond", "confidence": 0.8, "unit_id": unit_id, **fields}
        response = self.client.post(f"/api/internal/pages/{page['id']}/predictions", json=body, headers=INTERNAL)
        assert response.status_code == 201
        return response.json()

    def complete(self, kind: str, status: str = "terminé") -> None:
        self.client.post(
            f"/api/internal/execution-steps/{self.steps[kind]['id']}/complete",
            json={"status": status, "output": "ok"},
            headers=INTERNAL,
        )

    def first_run(self, *, cls_fp: str = FP_CLS_1, ext_fp: str = FP_EXT) -> dict[str, dict[str, Any]]:
        """Première exécution : une classification (page 1) et une extraction (nom)."""
        self.launch()
        cls = self.unit("classification", cls_fp, page_number=1)
        self.predict(self.pages[0], cls["id"], kind="label", name="CNI", value="CNI")
        self.client.post(
            f"/api/internal/analysis-units/{cls['id']}/complete", json={"status": "terminé"}, headers=INTERNAL
        )
        ext = self.unit("extraction", ext_fp, document_id=self.document_id, page_numbers=[1, 2])
        self.predict(self.pages[0], ext["id"])
        self.client.post(
            f"/api/internal/analysis-units/{ext['id']}/complete", json={"status": "terminé"}, headers=INTERNAL
        )
        self.complete("classification")
        self.complete("extraction")
        return {"classification": cls, "extraction": ext}

    # --- Lecture ---

    def current(self) -> dict[str, Any]:
        return self.client.get(f"/api/dossiers/{self.id}/analyse-dossier").json()

    def elements(self) -> list[dict[str, Any]]:
        return self.current()["elements"]

    def units(self, analysis_id: str | None = None) -> list[dict[str, Any]]:
        analysis_id = analysis_id or self.current()["id"]
        return self.client.get(f"/api/dossiers/{self.id}/analyses-dossier/{analysis_id}/units").json()

    def versions(self, element: dict[str, Any]) -> list[dict[str, Any]]:
        return self.client.get(
            f"/api/dossiers/{self.id}/analyses-dossier/{element['analysis_id']}/elements/{element['id']}/versions"
        ).json()

    def add_version(self, element: dict[str, Any], value: dict[str, Any], reason: str = "Corrigé") -> dict[str, Any]:
        response = self.client.post(
            f"/api/dossiers/{self.id}/analyses-dossier/{element['analysis_id']}/elements/{element['id']}/versions",
            json={"value": value, "reason": reason},
        )
        assert response.status_code == 201
        return response.json()


async def _delete_document(document_id: str) -> None:
    from sqlalchemy import text

    async with async_session_factory() as session:
        await session.execute(text("DELETE FROM dossier_documents WHERE id = :id"), {"id": document_id})
        await session.commit()


def _by_name(elements: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(e for e in elements if e["definition_name"] == name)


# --- Reprise d'une unité inchangée ---


def test_the_new_analysis_points_to_the_previous_one(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.first_run()
    first = dossier.current()
    dossier.stop_and_launch()
    second = dossier.current()
    assert second["sequence"] == 2
    analyses = client.get(f"/api/dossiers/{dossier.id}/analyses-dossier").json()
    assert [a["id"] for a in analyses] == [second["id"], first["id"]]
    assert first["previous_analysis_id"] is None


def test_first_run_never_reuses_anything(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.launch()
    unit = dossier.unit("classification", FP_CLS_1)
    assert unit["reused"] is False
    assert unit["reused_entities"] == []


def test_an_unchanged_unit_is_reused_with_all_its_elements_and_versions(client: TestClient) -> None:
    dossier = Dossier(client)
    first_units = dossier.first_run()
    before = dossier.elements()
    dossier.stop_and_launch()

    cls = dossier.unit("classification", FP_CLS_1, page_number=1)
    ext = dossier.unit("extraction", FP_EXT, document_id=dossier.document_id, page_numbers=[1, 2])

    assert cls["reused"] is True and ext["reused"] is True
    # L'extraction reprise indique ses entités (valeurs du modèle) pour la fusion des doublons.
    assert ext["reused_entities"] == [{"name": "nom", "value": "Dupond"}]
    units = {u["id"]: u for u in dossier.units()}
    reused = units[ext["id"]]
    assert reused["status"] == "terminé"
    assert reused["input_fingerprint"] == FP_EXT
    assert reused["element_count"] == 1
    assert reused["source_unit_id"] == first_units["extraction"]["id"]
    assert reused["description"]["page_numbers"] == [1, 2]

    after = dossier.elements()
    assert {e["kind"] for e in after} == {"classification", "entity"}
    nom = _by_name(after, "nom")
    original = _by_name(before, "nom")
    assert nom["id"] != original["id"]
    assert nom["origin_element_id"] == original["id"]
    assert nom["unit_id"] == ext["id"]
    # Un élément repris ne porte plus la prédiction (unique) : elle reste à l'original.
    assert nom["source_prediction_id"] is None
    assert nom["first_page_number"] == original["first_page_number"]
    assert nom["retained_version"]["value"] == {"value": "Dupond"}
    assert nom["retained_version"]["origin"] == "carried_over"  # résultat du modèle d'une autre exécution
    assert nom["retained_version"]["origin_version_id"] == original["retained_version"]["id"]
    assert nom["retained_version"]["confidence"] == 0.8
    assert nom["latest_model_version"]["id"] == nom["retained_version"]["id"]
    assert nom["needs_review"] is False


def test_an_instructor_value_survives_the_reuse_with_its_author_and_reason(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.first_run()
    nom = _by_name(dossier.elements(), "nom")
    dossier.add_version(nom, {"value": "Dupont"}, reason="Vérifié par téléphone")
    dossier.stop_and_launch()

    dossier.unit("classification", FP_CLS_1)
    dossier.unit("extraction", FP_EXT)

    carried = _by_name(dossier.elements(), "nom")
    assert carried["retained_version"]["value"] == {"value": "Dupont"}
    assert carried["retained_version"]["origin"] == "instructor"
    assert carried["retained_version"]["reason"] == "Vérifié par téléphone"
    assert carried["retained_version"]["author_id"]
    # La prédiction du modèle reste accessible, et l'historique est complet.
    assert carried["latest_model_version"]["value"] == {"value": "Dupond"}
    assert [v["version_number"] for v in dossier.versions(carried)] == [1, 2]
    assert [v["origin"] for v in dossier.versions(carried)] == ["carried_over", "instructor"]
    # Aucun « à revoir » : les entrées n'ont pas changé.
    assert carried["needs_review"] is False


def test_a_changed_fingerprint_is_not_reused(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.first_run()
    dossier.stop_and_launch()

    cls = dossier.unit("classification", FP_CLS_1)
    ext = dossier.unit("extraction", FP_EXT_CHANGED)

    assert cls["reused"] is True
    assert ext["reused"] is False  # recalculé par le worker
    assert ext["reused_entities"] == []
    assert [e["kind"] for e in dossier.elements()] == ["classification"]  # rien de copié pour l'unité recalculée


def test_a_unit_without_fingerprint_is_never_reused(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.first_run()
    dossier.stop_and_launch()
    assert dossier.unit("classification", None)["reused"] is False


def test_a_failed_unit_is_not_reused(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.launch()
    unit = dossier.unit("extraction", FP_EXT)
    client.post(f"/api/internal/analysis-units/{unit['id']}/complete", json={"status": "échec"}, headers=INTERNAL)
    dossier.stop_and_launch()
    assert dossier.unit("extraction", FP_EXT)["reused"] is False


def test_an_unchanged_unit_that_produced_nothing_is_reused_too(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.launch()
    unit = dossier.unit("extraction", FP_EXT)
    client.post(f"/api/internal/analysis-units/{unit['id']}/complete", json={"status": "terminé"}, headers=INTERNAL)
    dossier.stop_and_launch()

    again = dossier.unit("extraction", FP_EXT)

    assert again["reused"] is True and again["reused_entities"] == []
    [reused] = dossier.units()
    assert reused["element_count"] == 0 and reused["source_unit_id"] == unit["id"]


def test_two_identical_units_each_reuse_a_distinct_previous_unit(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.launch()
    # Deux pages identiques : même empreinte.
    first = dossier.unit("classification", FP_CLS_1, page_number=1)
    second = dossier.unit("classification", FP_CLS_1, page_number=2)
    for unit in (first, second):
        client.post(f"/api/internal/analysis-units/{unit['id']}/complete", json={"status": "terminé"}, headers=INTERNAL)
    dossier.stop_and_launch()

    a = dossier.unit("classification", FP_CLS_1, page_number=1)
    b = dossier.unit("classification", FP_CLS_1, page_number=2)
    c = dossier.unit("classification", FP_CLS_1, page_number=3)  # une page de plus : rien à reprendre

    sources = {u["id"]: u["source_unit_id"] for u in dossier.units()}
    assert (a["reused"], b["reused"], c["reused"]) == (True, True, False)
    assert {sources[a["id"]], sources[b["id"]]} == {first["id"], second["id"]}


def test_an_older_analysis_is_never_modified_by_the_reuse(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.first_run()
    first_id = dossier.current()["id"]
    before = dossier.elements()
    dossier.stop_and_launch()
    dossier.unit("classification", FP_CLS_1)
    dossier.unit("extraction", FP_EXT)

    after = client.get(f"/api/dossiers/{dossier.id}/analyses-dossier/{first_id}").json()["elements"]
    assert [e["id"] for e in after] == [e["id"] for e in before]
    assert [e["retained_version"]["id"] for e in after] == [e["retained_version"]["id"] for e in before]


# --- Valeurs validées d'une unité recalculée : conservées, « à revoir » ---


def test_a_validated_value_of_a_recomputed_unit_is_kept_and_flagged_for_review(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.first_run()
    nom = _by_name(dossier.elements(), "nom")
    dossier.add_version(nom, {"value": "Dupont"}, reason="Vérifié par téléphone")
    dossier.stop_and_launch()

    dossier.unit("classification", FP_CLS_1)
    ext = dossier.unit("extraction", FP_EXT_CHANGED)  # entrées modifiées : recalcul
    assert ext["reused"] is False
    # Le worker recalcule et dépose sa nouvelle valeur.
    dossier.predict(dossier.pages[0], ext["id"], value="Dupon")
    dossier.complete("classification")
    dossier.complete("extraction")

    elements = [e for e in dossier.elements() if e["definition_name"] == "nom"]
    carried = next(e for e in elements if e["origin_element_id"])
    fresh = next(e for e in elements if not e["origin_element_id"])
    # L'apport est conservé comme version retenue, signalé « à revoir » avec son motif.
    assert carried["retained_version"]["value"] == {"value": "Dupont"}
    assert carried["retained_version"]["origin"] == "instructor"
    assert carried["needs_review"] is True
    assert "entrées" in carried["review_reason"]
    assert carried["unit_id"] is None
    # La nouvelle valeur du modèle est produite à côté, sans rien écraser.
    assert fresh["retained_version"]["value"] == {"value": "Dupon"}
    assert fresh["needs_review"] is False
    # L'instructeur peut confirmer : le drapeau disparaît.
    dossier.add_version(carried, {"value": "Dupont"}, reason="Confirmé")
    assert _by_name([e for e in dossier.elements() if e["origin_element_id"]], "nom")["needs_review"] is False


def test_only_validated_values_are_carried_from_a_recomputed_unit(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.first_run()  # entité « nom » : valeur du modèle, jamais validée
    dossier.stop_and_launch()
    dossier.unit("classification", FP_CLS_1)
    ext = dossier.unit("extraction", FP_EXT_CHANGED)
    dossier.predict(dossier.pages[0], ext["id"], value="Dupon")
    dossier.complete("classification")
    dossier.complete("extraction")

    names = [(e["definition_name"], e["origin_element_id"] is not None) for e in dossier.elements()]
    # Rien d'ancien n'est conservé pour l'entité : le nouveau calcul la remplace.
    assert names.count(("nom", True)) == 0
    assert names.count(("nom", False)) == 1


def test_carry_over_is_idempotent(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.first_run()
    nom = _by_name(dossier.elements(), "nom")
    dossier.add_version(nom, {"value": "Dupont"})
    dossier.stop_and_launch()
    dossier.unit("classification", FP_CLS_1)
    dossier.unit("extraction", FP_EXT_CHANGED)
    dossier.complete("classification")
    dossier.complete("extraction")
    count = len(dossier.elements())

    dossier.complete("extraction")  # rejoué
    dossier.complete("classification")

    assert len(dossier.elements()) == count


def test_a_unit_of_a_removed_document_is_not_carried(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.first_run()
    nom = _by_name(dossier.elements(), "nom")
    dossier.add_version(nom, {"value": "Dupont"})
    dossier.stop_and_launch()
    # Le document de l'ancienne unité n'existe plus (aucune route de suppression : directement en base).
    client.portal.call(lambda: _delete_document(dossier.document_id))
    dossier.unit("classification", FP_CLS_1)
    dossier.unit("extraction", FP_EXT_CHANGED)
    dossier.complete("classification")
    dossier.complete("extraction")

    assert [e["definition_name"] for e in dossier.elements() if e["kind"] == "entity"] == []


def test_failed_step_carries_nothing(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.first_run()
    nom = _by_name(dossier.elements(), "nom")
    dossier.add_version(nom, {"value": "Dupont"})
    dossier.stop_and_launch()
    dossier.unit("extraction", FP_EXT_CHANGED)
    dossier.complete("extraction", "échec")
    assert [e for e in dossier.elements() if e["origin_element_id"]] == []


# --- Éléments ajoutés à la main et relations ---


def _manual(dossier: Dossier, kind: str, value: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    analysis_id = dossier.current()["id"]
    response = dossier.client.post(
        f"/api/dossiers/{dossier.id}/analyses-dossier/{analysis_id}/elements",
        json={"kind": kind, "value": value, "definition_name": name, "reason": "Ajouté à la main"},
    )
    assert response.status_code == 201
    return response.json()


def test_manual_elements_are_carried_to_the_new_analysis(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.first_run()
    manual = _manual(dossier, "field", {"value": "oui"}, "recevable")
    dossier.stop_and_launch()
    dossier.unit("classification", FP_CLS_1)
    dossier.unit("extraction", FP_EXT)
    dossier.complete("classification")
    dossier.complete("extraction")

    carried = _by_name(dossier.elements(), "recevable")
    assert carried["origin_element_id"] == manual["id"]
    assert carried["unit_id"] is None
    assert carried["retained_version"]["value"] == {"value": "oui"}
    assert carried["retained_version"]["origin"] == "instructor"
    assert carried["needs_review"] is False


def test_a_relation_is_carried_with_its_endpoints_remapped(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.first_run()
    elements = dossier.elements()
    cls = next(e for e in elements if e["kind"] == "classification")
    nom = _by_name(elements, "nom")
    relation = _manual(
        dossier,
        "relation",
        {"type": "décrit", "source_element_id": cls["id"], "target_element_id": nom["id"]},
        "décrit",
    )
    dossier.stop_and_launch()
    dossier.unit("classification", FP_CLS_1)
    dossier.unit("extraction", FP_EXT)
    dossier.complete("classification")
    dossier.complete("extraction")

    elements = dossier.elements()
    new_cls = next(e for e in elements if e["kind"] == "classification")
    new_nom = _by_name(elements, "nom")
    carried = next(e for e in elements if e["kind"] == "relation")
    assert carried["origin_element_id"] == relation["id"]
    value = carried["retained_version"]["value"]
    # Les extrémités pointent vers les copies de la nouvelle analyse, pas vers l'ancienne.
    assert value["source_element_id"] == new_cls["id"]
    assert value["target_element_id"] == new_nom["id"]
    assert value["type"] == "décrit"


def test_a_relation_whose_endpoint_is_gone_is_not_carried(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.first_run()
    elements = dossier.elements()
    cls = next(e for e in elements if e["kind"] == "classification")
    nom = _by_name(elements, "nom")
    _manual(
        dossier,
        "relation",
        {"type": "décrit", "source_element_id": cls["id"], "target_element_id": nom["id"]},
        "décrit",
    )
    dossier.stop_and_launch()
    dossier.unit("classification", FP_CLS_1)
    ext = dossier.unit("extraction", FP_EXT_CHANGED)  # « nom » est recalculé : plus de copie de l'extrémité
    dossier.predict(dossier.pages[0], ext["id"], value="Dupon")
    dossier.complete("classification")
    dossier.complete("extraction")

    assert [e for e in dossier.elements() if e["kind"] == "relation"] == []


def test_manual_elements_wait_for_both_steps_before_being_carried(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.first_run()
    _manual(dossier, "field", {"value": "oui"}, "recevable")
    dossier.stop_and_launch()
    dossier.unit("classification", FP_CLS_1)
    dossier.complete("classification")
    assert [e for e in dossier.elements() if e["definition_name"] == "recevable"] == []  # extraction pas finie
    dossier.unit("extraction", FP_EXT)
    dossier.complete("extraction")
    assert len([e for e in dossier.elements() if e["definition_name"] == "recevable"]) == 1


def test_the_chain_of_relaunches_keeps_carrying_manual_elements(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.first_run()
    _manual(dossier, "field", {"value": "oui"}, "recevable")
    for _ in range(2):
        dossier.stop_and_launch()
        dossier.unit("classification", FP_CLS_1)
        dossier.unit("extraction", FP_EXT)
        dossier.complete("classification")
        dossier.complete("extraction")
    assert dossier.current()["sequence"] == 3
    assert len([e for e in dossier.elements() if e["definition_name"] == "recevable"]) == 1


# --- Agents et synthèses ---


def _agent_reuse(dossier: Dossier) -> dict[str, Any]:
    response = dossier.client.post(
        f"/api/internal/dossiers/{dossier.id}/agent-units/reuse",
        json={"step_id": dossier.steps["agent"]["id"]},
        headers=INTERNAL,
    )
    assert response.status_code == 200
    return response.json()


def _finish_agent(dossier: Dossier, output: str = "Les pièces sont cohérentes.") -> None:
    dossier.client.post(
        f"/api/internal/execution-steps/{dossier.steps['agent']['id']}/complete",
        json={"status": "terminé", "output": output},
        headers=INTERNAL,
    )


def test_an_unchanged_agent_reuses_its_synthesis_without_the_llm(client: TestClient) -> None:
    dossier = Dossier(client, agent="Cohérence")
    dossier.first_run()
    _finish_agent(dossier)
    dossier.stop_and_launch()
    dossier.unit("classification", FP_CLS_1)
    dossier.unit("extraction", FP_EXT)
    dossier.complete("classification")
    dossier.complete("extraction")

    reuse = _agent_reuse(dossier)

    assert reuse == {"reused": True, "output": "Les pièces sont cohérentes."}
    synthesis = next(e for e in dossier.elements() if e["kind"] == "synthesis")
    assert synthesis["definition_name"] == "Cohérence"
    assert synthesis["origin_element_id"] is not None
    assert synthesis["retained_version"]["value"] == {"text": "Les pièces sont cohérentes."}
    agent_unit = next(u for u in dossier.units() if u["kind"] == "agent")
    assert agent_unit["status"] == "terminé" and agent_unit["source_unit_id"] is not None
    assert agent_unit["description"]["step_id"] == dossier.steps["agent"]["id"]
    # Le worker termine l'étape avec cette sortie : pas de doublon de synthèse.
    _finish_agent(dossier, reuse["output"])
    assert len([e for e in dossier.elements() if e["kind"] == "synthesis"]) == 1
    assert len([u for u in dossier.units() if u["kind"] == "agent"]) == 1


def test_an_agent_is_recomputed_when_what_it_reads_changed(client: TestClient) -> None:
    dossier = Dossier(client, agent="Cohérence")
    dossier.first_run()
    _finish_agent(dossier)
    dossier.stop_and_launch()
    dossier.unit("classification", FP_CLS_1)
    ext = dossier.unit("extraction", FP_EXT_CHANGED)  # une entrée de l'agent a changé
    dossier.predict(dossier.pages[0], ext["id"], value="Dupon")
    dossier.complete("classification")
    dossier.complete("extraction")

    assert _agent_reuse(dossier) == {"reused": False, "output": None}
    assert [e for e in dossier.elements() if e["kind"] == "synthesis"] == []


def test_an_agent_is_recomputed_when_its_prompt_changed(client: TestClient) -> None:
    dossier = Dossier(client, agent="Cohérence")
    dossier.first_run()
    _finish_agent(dossier)
    agent_id = client.get(f"/api/analyses/{dossier.analyse_id}").json()["agents"][0]["id"]
    client.put(f"/api/analyses/{dossier.analyse_id}/agents/{agent_id}/prompt", json={"prompt": "Vérifie autre chose."})
    dossier.stop_and_launch()
    dossier.unit("classification", FP_CLS_1)
    dossier.unit("extraction", FP_EXT)
    dossier.complete("classification")
    dossier.complete("extraction")
    assert _agent_reuse(dossier)["reused"] is False


def test_agent_reuse_is_refused_without_a_previous_analysis_or_for_an_unknown_step(client: TestClient) -> None:
    dossier = Dossier(client, agent="Cohérence")
    dossier.launch()
    assert _agent_reuse(dossier) == {"reused": False, "output": None}
    unknown = client.post(
        f"/api/internal/dossiers/{dossier.id}/agent-units/reuse", json={"step_id": str(uuid.uuid4())}, headers=INTERNAL
    )
    assert unknown.json() == {"reused": False, "output": None}
    bad = {"X-App-Token": "not-a-valid-token"}
    refused = client.post(
        f"/api/internal/dossiers/{dossier.id}/agent-units/reuse",
        json={"step_id": dossier.steps["agent"]["id"]},
        headers=bad,
    )
    assert refused.status_code == 401


def test_correcting_an_element_flags_the_syntheses_to_regenerate(client: TestClient) -> None:
    dossier = Dossier(client, agent="Cohérence")
    dossier.first_run()
    _finish_agent(dossier)
    synthesis = next(e for e in dossier.elements() if e["kind"] == "synthesis")
    assert synthesis["needs_review"] is False

    dossier.add_version(_by_name(dossier.elements(), "nom"), {"value": "Dupont"}, reason="Corrigé")

    synthesis = next(e for e in dossier.elements() if e["kind"] == "synthesis")
    assert synthesis["needs_review"] is True
    assert "régénérer" in synthesis["review_reason"]
    # Elle n'est jamais régénérée automatiquement ; l'instructeur la confirme ou la corrige.
    assert synthesis["retained_version"]["value"] == {"text": "Les pièces sont cohérentes."}
    dossier.add_version(synthesis, {"text": "Cohérentes, nom corrigé."}, reason="Mise à jour")
    synthesis = next(e for e in dossier.elements() if e["kind"] == "synthesis")
    assert synthesis["needs_review"] is False


def test_correcting_a_synthesis_does_not_flag_other_syntheses(client: TestClient) -> None:
    dossier = Dossier(client, agent="Cohérence")
    dossier.first_run()
    _finish_agent(dossier)
    synthesis = next(e for e in dossier.elements() if e["kind"] == "synthesis")
    dossier.add_version(synthesis, {"text": "Autre texte"}, reason="r")
    assert next(e for e in dossier.elements() if e["kind"] == "synthesis")["needs_review"] is False


def test_a_flagged_synthesis_keeps_its_flag_when_reused(client: TestClient) -> None:
    dossier = Dossier(client, agent="Cohérence")
    dossier.first_run()
    _finish_agent(dossier)
    dossier.add_version(_by_name(dossier.elements(), "nom"), {"value": "Dupont"}, reason="Corrigé")
    dossier.stop_and_launch()
    dossier.unit("classification", FP_CLS_1)
    dossier.unit("extraction", FP_EXT)
    dossier.complete("classification")
    dossier.complete("extraction")

    assert _agent_reuse(dossier)["reused"] is True
    synthesis = next(e for e in dossier.elements() if e["kind"] == "synthesis")
    assert synthesis["needs_review"] is True and "régénérer" in synthesis["review_reason"]


# --- Une relance sans aucun changement ne recalcule rien ---


def test_an_unchanged_relaunch_reuses_everything(client: TestClient) -> None:
    dossier = Dossier(client, agent="Cohérence")
    dossier.first_run()
    _finish_agent(dossier)
    nom = _by_name(dossier.elements(), "nom")
    dossier.add_version(nom, {"value": "Dupont"}, reason="Vérifié")
    before = {(e["kind"], e["definition_name"]) for e in dossier.elements()}
    dossier.stop_and_launch()

    flags = [
        dossier.unit("classification", FP_CLS_1)["reused"],
        dossier.unit("extraction", FP_EXT)["reused"],
    ]
    dossier.complete("classification")
    dossier.complete("extraction")
    flags.append(_agent_reuse(dossier)["reused"])

    assert flags == [True, True, True]  # aucun appel au LLM nécessaire
    assert {(e["kind"], e["definition_name"]) for e in dossier.elements()} == before
    assert all(e["origin_element_id"] for e in dossier.elements())
    assert all(u["source_unit_id"] for u in dossier.units())
    # Le seul élément marqué est la synthèse à régénérer (une valeur a été corrigée après sa production).
    assert [e["kind"] for e in dossier.elements() if e["needs_review"]] == ["synthesis"]


async def _count_elements(analysis_id: uuid.UUID) -> int:
    from sqlalchemy import func, select

    async with async_session_factory() as session:
        return (
            await session.execute(
                select(func.count()).select_from(AnalysisElement).where(AnalysisElement.analysis_id == analysis_id)
            )
        ).scalar_one()


def test_reused_elements_are_real_copies_not_shared_rows(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.first_run()
    first = dossier.current()
    dossier.stop_and_launch()
    dossier.unit("classification", FP_CLS_1)
    dossier.unit("extraction", FP_EXT)
    second = dossier.current()

    assert client.portal.call(lambda: _count_elements(uuid.UUID(first["id"]))) == 2
    assert client.portal.call(lambda: _count_elements(uuid.UUID(second["id"]))) == 2
    # Modifier la copie ne touche pas l'original.
    nom = _by_name(dossier.elements(), "nom")
    dossier.add_version(nom, {"value": "Dupont"})
    original = client.get(f"/api/dossiers/{dossier.id}/analyses-dossier/{first['id']}").json()["elements"]
    assert _by_name(original, "nom")["retained_version"]["value"] == {"value": "Dupond"}


# --- Éléments sans unité issus du modèle (exécutions antérieures au suivi, rattrapage #120) ---


def test_a_validated_model_element_without_unit_is_carried_for_review(client: TestClient) -> None:
    """Une prédiction déposée sans unité (ancien worker) puis validée : son élément
    n'a pas d'unité. À la relance, la valeur validée est conservée « à revoir » ; un
    résultat du modèle sans apport n'est pas conservé (le nouveau calcul le remplace)."""
    dossier = Dossier(client)
    dossier.launch()
    prediction = client.post(
        f"/api/internal/pages/{dossier.pages[0]['id']}/predictions",
        json={"kind": "entity", "name": "nom", "value": "Dupond", "confidence": 0.8},
        headers=INTERNAL,
    ).json()
    client.put(
        f"/api/dossiers/{dossier.id}/documents/{dossier.document_id}/pages/{dossier.pages[0]['id']}"
        f"/predictions/{prediction['id']}/validations",
        json={"status": "corrigé", "corrected_value": "Dupont"},
    )
    [original] = dossier.elements()
    assert original["unit_id"] is None and original["source_prediction_id"] == prediction["id"]
    dossier.complete("classification")
    dossier.complete("extraction")
    dossier.stop_and_launch()
    dossier.unit("classification", FP_CLS_1)
    dossier.unit("extraction", FP_EXT)
    dossier.complete("classification")
    dossier.complete("extraction")

    [carried] = dossier.elements()
    assert carried["origin_element_id"] == original["id"]
    assert carried["retained_version"]["value"] == {"value": "Dupont"}
    assert carried["retained_version"]["origin"] == "instructor"
    assert carried["needs_review"] is True
    assert "suivies" in carried["review_reason"]
    assert carried["source_prediction_id"] is None


def test_an_unvalidated_model_element_without_unit_is_not_carried(client: TestClient) -> None:
    dossier = Dossier(client)
    dossier.launch()
    analysis_id = dossier.current()["id"]
    prediction = client.post(
        f"/api/internal/pages/{dossier.pages[0]['id']}/predictions",
        json={"kind": "entity", "name": "nom", "value": "Dupond", "confidence": 0.8},
        headers=INTERNAL,
    ).json()

    async def add_model_element() -> None:
        from app.models.dossier_analysis import AnalysisElementKind, DossierAnalysis, ElementVersionOrigin
        from app.repositories.dossier_analysis_repository import DossierAnalysisRepository

        async with async_session_factory() as session:
            analysis = await session.get(DossierAnalysis, uuid.UUID(analysis_id))
            await DossierAnalysisRepository(session).create_element(
                analysis,
                kind=AnalysisElementKind.ENTITY,
                value={"value": "Dupond"},
                origin=ElementVersionOrigin.MODEL,
                definition_name="nom",
                source_prediction_id=uuid.UUID(prediction["id"]),
            )

    client.portal.call(add_model_element)
    assert len(dossier.elements()) == 1  # il existe dans l'exécution 1, issu du modèle, sans apport
    dossier.complete("classification")
    dossier.complete("extraction")
    dossier.stop_and_launch()
    dossier.unit("classification", FP_CLS_1)
    dossier.unit("extraction", FP_EXT)
    dossier.complete("classification")
    dossier.complete("extraction")

    # Aucune valeur d'instructeur : le nouveau calcul le remplacerait, rien n'est conservé.
    assert dossier.elements() == []
