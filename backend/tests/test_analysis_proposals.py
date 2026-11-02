"""Tests des propositions de modification de l'analyse de dossier (issue #114)."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi.testclient import TestClient

from app.agent.analysis_tools import AnalysisProposer
from app.db import async_session_factory
from app.models.dossier_analysis import (
    AnalysisElement,
    AnalysisElementKind,
    DossierAnalysis,
    DossierAnalysisStatus,
    ElementVersionOrigin,
)
from app.repositories.dossier_analysis_repository import DossierAnalysisRepository
from tests.agent_support import internal_conversation


def _create_dossier(client: TestClient, name: str = "Dossier propositions") -> str:
    analyse_id = client.post("/api/analyses", json={"name": "Analyse", "description": "Test"}).json()["id"]
    return client.post("/api/dossiers", json={"name": name, "analyse_id": analyse_id}).json()["id"]


def _run(client: TestClient, work: Callable[[DossierAnalysisRepository], Awaitable[Any]]) -> Any:
    async def runner() -> Any:
        async with async_session_factory() as session:
            return await work(DossierAnalysisRepository(session))

    return client.portal.call(runner)


def _setup(client: TestClient, value: str = "Dupond") -> tuple[str, DossierAnalysis, AnalysisElement]:
    dossier_id = _create_dossier(client)
    analysis = _run(client, lambda repo: repo.create_analysis(uuid.UUID(dossier_id)))
    element = _run(
        client,
        lambda repo: repo.create_element(
            analysis,
            kind=AnalysisElementKind.ENTITY,
            value={"value": value},
            definition_name="nom",
            origin=ElementVersionOrigin.MODEL,
        ),
    )
    return dossier_id, analysis, element


def _base(dossier_id: str, analysis_id: Any) -> str:
    return f"/api/dossiers/{dossier_id}/analyses-dossier/{analysis_id}"


def _propose(
    client: TestClient, dossier_id: str, analysis_id: Any, element_id: Any, value: str = "Dupont", **extra: Any
):
    return client.post(
        f"{_base(dossier_id, analysis_id)}/proposals",
        json={"element_id": str(element_id), "value": {"value": value}, "reason": "Vérifié par téléphone", **extra},
    )


def _element(client: TestClient, dossier_id: str, element_id: Any) -> dict[str, Any]:
    elements = client.get(f"/api/dossiers/{dossier_id}/analyse-dossier").json()["elements"]
    return next(e for e in elements if e["id"] == str(element_id))


# --- Une proposition n'applique rien ---


def test_proposal_does_not_change_the_analysis(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)

    response = _propose(
        client,
        dossier_id,
        analysis.id,
        element.id,
        source_type="chat_message",
        source_id=str(uuid.uuid4()),
        model="llm-test",
        prompt_version="v3",
    )
    assert response.status_code == 201
    proposal = response.json()
    assert proposal["status"] == "pending"
    assert proposal["element_id"] == str(element.id)
    assert proposal["kind"] == "entity"
    assert proposal["definition_name"] == "nom"
    assert proposal["proposed_value"] == {"value": "Dupont"}
    assert proposal["proposed_by"]
    assert proposal["model"] == "llm-test"
    assert proposal["prompt_version"] == "v3"
    assert proposal["decided_by"] is None

    out = _element(client, dossier_id, element.id)
    assert out["retained_version"]["value"] == {"value": "Dupond"}
    versions = client.get(f"{_base(dossier_id, analysis.id)}/elements/{element.id}/versions").json()
    assert len(versions) == 1


def test_proposal_is_logged_when_created(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)
    proposal = _propose(client, dossier_id, analysis.id, element.id, model="m", prompt_version="p").json()

    detail = client.get(f"{_base(dossier_id, analysis.id)}/proposals/{proposal['id']}").json()
    [event] = detail["events"]
    assert event["kind"] == "proposed"
    assert event["value"] == {"value": "Dupont"}
    assert event["note"] == "Vérifié par téléphone"
    assert event["duration_seconds"] is None
    assert (event["model"], event["prompt_version"]) == ("m", "p")


# --- Accepter ---


def test_accept_creates_a_version_with_the_proposal_as_source(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)
    proposal = _propose(client, dossier_id, analysis.id, element.id).json()

    response = client.post(f"{_base(dossier_id, analysis.id)}/proposals/{proposal['id']}/accept")
    assert response.status_code == 200
    accepted = response.json()
    assert accepted["status"] == "accepted"
    assert accepted["decided_by"]
    assert accepted["decided_at"]
    assert accepted["resulting_version_id"]

    out = _element(client, dossier_id, element.id)
    assert out["retained_version"]["id"] == accepted["resulting_version_id"]
    assert out["retained_version"]["value"] == {"value": "Dupont"}
    assert out["retained_version"]["origin"] == "instructor"
    assert out["retained_version"]["reason"] == "Vérifié par téléphone"
    assert out["retained_version"]["source_type"] == "proposal"
    assert out["retained_version"]["source_id"] == proposal["id"]
    # La prédiction du modèle reste conservée.
    assert out["latest_model_version"]["value"] == {"value": "Dupond"}


def test_decision_is_logged_with_final_value_and_duration(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)
    proposal = _propose(client, dossier_id, analysis.id, element.id, model="m", prompt_version="p").json()
    client.post(f"{_base(dossier_id, analysis.id)}/proposals/{proposal['id']}/accept")

    events = client.get(f"{_base(dossier_id, analysis.id)}/proposals/{proposal['id']}").json()["events"]
    assert [e["kind"] for e in events] == ["proposed", "accepted"]
    decision = events[1]
    assert decision["value"] == {"value": "Dupont"}
    assert decision["actor_id"]
    assert decision["duration_seconds"] is not None and decision["duration_seconds"] >= 0
    assert (decision["model"], decision["prompt_version"]) == ("m", "p")


# --- Modifier ---


def test_modify_applies_another_value(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)
    proposal = _propose(client, dossier_id, analysis.id, element.id, value="Dupon").json()

    response = client.post(
        f"{_base(dossier_id, analysis.id)}/proposals/{proposal['id']}/modify",
        json={"value": {"value": "Dupont"}, "reason": "Orthographe correcte"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "modified"
    assert _element(client, dossier_id, element.id)["retained_version"]["value"] == {"value": "Dupont"}

    events = client.get(f"{_base(dossier_id, analysis.id)}/proposals/{proposal['id']}").json()["events"]
    assert [e["kind"] for e in events] == ["proposed", "modified"]
    # Le journal garde la valeur proposée et la valeur finale.
    assert events[0]["value"] == {"value": "Dupon"}
    assert events[1]["value"] == {"value": "Dupont"}
    assert events[1]["note"] == "Orthographe correcte"


def test_modify_validates_the_value(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)
    proposal = _propose(client, dossier_id, analysis.id, element.id).json()
    response = client.post(
        f"{_base(dossier_id, analysis.id)}/proposals/{proposal['id']}/modify", json={"value": {"label": "x"}}
    )
    assert response.status_code == 422
    # Rien n'a été appliqué, la proposition reste en attente.
    assert _element(client, dossier_id, element.id)["retained_version"]["value"] == {"value": "Dupond"}
    assert client.get(f"{_base(dossier_id, analysis.id)}/proposals/{proposal['id']}").json()["status"] == "pending"


# --- Rejeter ---


def test_reject_applies_nothing(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)
    proposal = _propose(client, dossier_id, analysis.id, element.id).json()

    response = client.post(
        f"{_base(dossier_id, analysis.id)}/proposals/{proposal['id']}/reject", json={"reason": "Pas la bonne personne"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["resulting_version_id"] is None
    assert _element(client, dossier_id, element.id)["retained_version"]["value"] == {"value": "Dupond"}
    versions = client.get(f"{_base(dossier_id, analysis.id)}/elements/{element.id}/versions").json()
    assert len(versions) == 1

    events = client.get(f"{_base(dossier_id, analysis.id)}/proposals/{proposal['id']}").json()["events"]
    assert [e["kind"] for e in events] == ["proposed", "rejected"]
    assert events[1]["note"] == "Pas la bonne personne"


# --- Une seule décision ---


def test_a_decided_proposal_cannot_be_decided_again(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)
    proposal = _propose(client, dossier_id, analysis.id, element.id).json()
    base = f"{_base(dossier_id, analysis.id)}/proposals/{proposal['id']}"
    assert client.post(f"{base}/accept").status_code == 200

    assert client.post(f"{base}/accept").status_code == 409
    assert client.post(f"{base}/modify", json={"value": {"value": "X"}}).status_code == 409
    assert client.post(f"{base}/reject", json={}).status_code == 409
    versions = client.get(f"{_base(dossier_id, analysis.id)}/elements/{element.id}/versions").json()
    assert len(versions) == 2


# --- Conflit de version ---


def test_proposal_on_an_element_changed_since_is_reported_not_applied(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)
    proposal = _propose(client, dossier_id, analysis.id, element.id, value="Dupont").json()
    # Un autre instructeur corrige l'élément entre-temps.
    client.post(
        f"{_base(dossier_id, analysis.id)}/elements/{element.id}/versions",
        json={"value": {"value": "Durand"}, "reason": "Autre correction"},
    )

    base = f"{_base(dossier_id, analysis.id)}/proposals/{proposal['id']}"
    for action in (
        lambda: client.post(f"{base}/accept"),
        lambda: client.post(f"{base}/modify", json={"value": {"value": "X"}}),
    ):
        response = action()
        assert response.status_code == 409
        assert "modifié" in response.json()["detail"]

    assert _element(client, dossier_id, element.id)["retained_version"]["value"] == {"value": "Durand"}
    # La proposition reste en attente et peut être rejetée.
    assert client.get(base).json()["status"] == "pending"
    assert client.post(f"{base}/reject", json={}).status_code == 200


# --- Proposer de créer un élément ---


def test_proposal_can_create_a_new_element(client: TestClient) -> None:
    dossier_id, analysis, _ = _setup(client)
    response = client.post(
        f"{_base(dossier_id, analysis.id)}/proposals",
        json={
            "kind": "entity",
            "definition_name": "adresse",
            "value": {"value": "12 rue des Lilas"},
            "reason": "Relevé sur le justificatif",
        },
    )
    assert response.status_code == 201
    proposal = response.json()
    assert proposal["element_id"] is None
    assert len(client.get(f"/api/dossiers/{dossier_id}/analyse-dossier").json()["elements"]) == 1

    accepted = client.post(f"{_base(dossier_id, analysis.id)}/proposals/{proposal['id']}/accept").json()
    assert accepted["resulting_element_id"]
    elements = client.get(f"/api/dossiers/{dossier_id}/analyse-dossier").json()["elements"]
    created = next(e for e in elements if e["id"] == accepted["resulting_element_id"])
    assert created["definition_name"] == "adresse"
    assert created["retained_version"]["value"] == {"value": "12 rue des Lilas"}
    assert created["retained_version"]["source_id"] == proposal["id"]


# --- Validation à la création ---


def test_proposal_needs_either_an_element_or_a_kind(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)
    url = f"{_base(dossier_id, analysis.id)}/proposals"
    assert client.post(url, json={"value": {"value": "X"}, "reason": "r"}).status_code == 422
    both = {"element_id": str(element.id), "kind": "entity", "value": {"value": "X"}, "reason": "r"}
    assert client.post(url, json=both).status_code == 422


def test_proposal_requires_a_reason_and_a_valid_value(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)
    url = f"{_base(dossier_id, analysis.id)}/proposals"
    assert client.post(url, json={"element_id": str(element.id), "value": {"value": "X"}}).status_code == 422
    wrong_shape = {"element_id": str(element.id), "value": {"label": "X"}, "reason": "r"}
    assert client.post(url, json=wrong_shape).status_code == 422


def test_proposal_on_unknown_element_is_404(client: TestClient) -> None:
    dossier_id, analysis, _ = _setup(client)
    assert _propose(client, dossier_id, analysis.id, uuid.uuid4()).status_code == 404


# --- Liste et isolation ---


def test_list_proposals_filters_by_status(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)
    first = _propose(client, dossier_id, analysis.id, element.id, value="A").json()
    second = _propose(client, dossier_id, analysis.id, element.id, value="B").json()
    client.post(f"{_base(dossier_id, analysis.id)}/proposals/{first['id']}/reject", json={})

    base = f"{_base(dossier_id, analysis.id)}/proposals"
    assert {p["id"] for p in client.get(base).json()} == {first["id"], second["id"]}
    assert [p["id"] for p in client.get(f"{base}?status=pending").json()] == [second["id"]]
    assert [p["id"] for p in client.get(f"{base}?status=rejected").json()] == [first["id"]]
    # Raccourci : propositions en attente de l'analyse courante du dossier.
    current = client.get(f"/api/dossiers/{dossier_id}/analyse-dossier/proposals").json()
    assert [p["id"] for p in current] == [second["id"]]


def test_proposals_of_another_dossier_are_not_reachable(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)
    proposal = _propose(client, dossier_id, analysis.id, element.id).json()
    other = _create_dossier(client, "Autre dossier")
    base = f"{_base(other, analysis.id)}/proposals"

    assert client.get(base).status_code == 404
    assert client.get(f"{base}/{proposal['id']}").status_code == 404
    assert client.post(f"{base}/{proposal['id']}/accept").status_code == 404
    assert _propose(client, other, analysis.id, element.id).status_code == 404


def test_unknown_proposal_is_404(client: TestClient) -> None:
    dossier_id, analysis, _ = _setup(client)
    base = f"{_base(dossier_id, analysis.id)}/proposals/{uuid.uuid4()}"
    assert client.get(base).status_code == 404
    assert client.post(f"{base}/accept").status_code == 404


def test_current_proposals_without_analysis_is_404(client: TestClient) -> None:
    dossier_id = _create_dossier(client)
    assert client.get(f"/api/dossiers/{dossier_id}/analyse-dossier/proposals").status_code == 404


# --- Analyse figée ---


def test_frozen_analysis_rejects_proposals_and_decisions(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)
    proposal = _propose(client, dossier_id, analysis.id, element.id).json()

    async def freeze(repo: DossierAnalysisRepository) -> None:
        row = await repo.db.get(DossierAnalysis, analysis.id)
        row.status = DossierAnalysisStatus.FIGEE
        await repo.db.commit()

    _run(client, freeze)

    base = f"{_base(dossier_id, analysis.id)}/proposals"
    assert _propose(client, dossier_id, analysis.id, element.id).status_code == 409
    assert client.post(f"{base}/{proposal['id']}/accept").status_code == 409
    assert client.post(f"{base}/{proposal['id']}/reject", json={}).status_code == 409
    # La lecture reste possible.
    assert client.get(f"{base}/{proposal['id']}").json()["status"] == "pending"


# --- Le chat propose pour le compte d'un utilisateur (issue #115) ---


def _chat_proposer(dossier_id: str, **overrides: Any) -> AnalysisProposer:
    params = {"dossier_id": dossier_id, "user_id": "user-42", "model": "llm-test", "source_message_id": None}
    return AnalysisProposer(**{**params, **overrides})


def _chat_proposes(client: TestClient, proposer: AnalysisProposer, **proposal: Any) -> str:
    async def run_proposal() -> str:
        await proposer.load()
        return await proposer.propose(**proposal)

    return client.portal.call(run_proposal)


def test_chat_proposal_is_stored_pending_for_the_given_user(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)
    message_id = str(uuid.uuid4())
    proposer = _chat_proposer(dossier_id, source_message_id=message_id)

    answer = _chat_proposes(
        client, proposer, element_id=str(element.id), value="Dupont", reason="L'instructeur a vérifié la pièce"
    )

    assert "EN ATTENTE" in answer and len(proposer.proposal_ids) == 1
    # Rien n'est appliqué : l'utilisateur doit accepter.
    assert _element(client, dossier_id, element.id)["retained_version"]["value"] == {"value": "Dupond"}
    # La proposition est visible côté utilisateur, avec ses traces, et peut être acceptée.
    [proposal] = client.get(f"/api/dossiers/{dossier_id}/analyse-dossier/proposals").json()
    assert proposal["id"] == proposer.proposal_ids[0] and proposal["analysis_id"] == str(analysis.id)
    assert proposal["status"] == "pending" and proposal["proposed_by"] == "chat-agent:user-42"
    assert (proposal["source_type"], proposal["source_id"]) == ("chat_message", message_id)
    assert (proposal["model"], proposal["prompt_version"]) == ("llm-test", "chat-v2")
    accepted = client.post(f"{_base(dossier_id, analysis.id)}/proposals/{proposal['id']}/accept")
    assert accepted.status_code == 200
    assert _element(client, dossier_id, element.id)["retained_version"]["value"] == {"value": "Dupont"}


def test_chat_proposal_can_add_a_new_element(client: TestClient) -> None:
    dossier_id, _, _ = _setup(client)
    proposer = _chat_proposer(dossier_id)

    _chat_proposes(client, proposer, kind="entity", name="téléphone", value="06 12 34 56 78", reason="Au téléphone")

    [proposal] = client.get(f"/api/dossiers/{dossier_id}/analyse-dossier/proposals").json()
    assert proposal["element_id"] is None and proposal["definition_name"] == "téléphone"
    assert proposal["proposed_value"] == {"value": "06 12 34 56 78"}


def test_chat_proposal_errors_are_told_to_the_model(client: TestClient) -> None:
    dossier_id, _, element = _setup(client)
    proposer = _chat_proposer(dossier_id)
    unknown = _chat_proposes(client, proposer, element_id=str(uuid.uuid4()), value="X", reason="r")
    assert "introuvable" in unknown and proposer.proposal_ids == []

    never_launched = _create_dossier(client, "Sans analyse")
    missing = _chat_proposes(client, _chat_proposer(never_launched), kind="entity", name="n", value="X", reason="r")
    assert "pas encore d'analyse" in missing


def test_internal_conversation_exposes_its_user(client: TestClient) -> None:
    dossier_id = _create_dossier(client)
    conversation = client.post(f"/api/dossiers/{dossier_id}/conversations").json()
    internal = internal_conversation(client, conversation["id"])
    assert internal["user_id"] == conversation["user_id"]


# --- Une proposition en attente identique n'est pas dupliquée (issue #117) ---


def test_an_identical_pending_proposal_is_returned_instead_of_duplicated(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)
    first = _propose(client, dossier_id, analysis.id, element.id, value="Dupont").json()
    again = _propose(client, dossier_id, analysis.id, element.id, value="Dupont")

    assert again.status_code == 201
    assert again.json()["id"] == first["id"]
    assert len(client.get(f"{_base(dossier_id, analysis.id)}/proposals").json()) == 1
    # Une autre valeur reste une autre proposition.
    other = _propose(client, dossier_id, analysis.id, element.id, value="Durand").json()
    assert other["id"] != first["id"]


def test_a_decided_proposal_does_not_block_a_new_identical_one(client: TestClient) -> None:
    dossier_id, analysis, element = _setup(client)
    first = _propose(client, dossier_id, analysis.id, element.id, value="Dupont").json()
    client.post(f"{_base(dossier_id, analysis.id)}/proposals/{first['id']}/reject", json={})
    second = _propose(client, dossier_id, analysis.id, element.id, value="Dupont").json()
    assert second["id"] != first["id"]
    assert second["status"] == "pending"


def test_identical_new_element_proposals_are_not_duplicated(client: TestClient) -> None:
    dossier_id, analysis, _ = _setup(client)
    url = f"{_base(dossier_id, analysis.id)}/proposals"
    body = {"kind": "entity", "definition_name": "téléphone", "value": {"value": "06"}, "reason": "r"}
    first = client.post(url, json=body).json()
    again = client.post(url, json=body).json()
    other_name = client.post(url, json={**body, "definition_name": "fax"}).json()
    assert again["id"] == first["id"]
    assert other_name["id"] != first["id"]
