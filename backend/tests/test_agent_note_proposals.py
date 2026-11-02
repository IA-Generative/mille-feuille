"""Analyse d'une note interne par l'agent (issue #117) : le LLM est simulé, la base est réelle.

Les travaux tournent sur la boucle de l'application (`client.portal`), celle qui possède le moteur de base."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.agent.jobs import note_proposals as note_job
from app.agent.jobs.note_proposals import propose_from_note
from app.agent.llm import ProposedUpdate, ProposedUpdates
from app.db import async_session_factory
from app.models.dossier_analysis import AnalysisElementKind, ElementVersionOrigin
from app.repositories.dossier_analysis_repository import DossierAnalysisRepository
from app.repositories.dossier_note_repository import DossierNoteRepository

CONTENT = "J'ai appelé l'usager : le nom est bien Dupont. Son téléphone est le 06 12 34 56 78."


def _setup(client: TestClient, name: str, *, with_analysis: bool = True, archived: bool = False) -> dict:
    analyse_id = client.post("/api/analyses", json={"name": f"Analyse {name}", "description": "Test"}).json()["id"]
    dossier_id = client.post("/api/dossiers", json={"name": name, "analyse_id": analyse_id}).json()["id"]

    async def setup() -> dict:
        async with async_session_factory() as db:
            ids: dict = {"dossier": dossier_id}
            if with_analysis:
                analyses = DossierAnalysisRepository(db)
                analysis = await analyses.create_analysis(uuid.UUID(dossier_id))
                for key, (definition, value) in {"nom": ("nom", "Dupond"), "adresse": ("adresse", "1 rue X")}.items():
                    element = await analyses.create_element(
                        analysis,
                        kind=AnalysisElementKind.ENTITY,
                        value={"value": value},
                        definition_name=definition,
                        origin=ElementVersionOrigin.MODEL,
                    )
                    ids[key] = str(element.id)
            notes = DossierNoteRepository(db)
            note = await notes.create(uuid.UUID(dossier_id), content=CONTENT, user_id="user-42")
            note = await notes.start_analysis(note, user_id="user-42")
            if archived:
                note = await notes.set_archived(note, True)
            ids["note"] = str(note.id)
            return ids

    return client.portal.call(setup)


def _note(client: TestClient, ids: dict) -> dict:
    async def read() -> dict:
        async with async_session_factory() as db:
            note = await DossierNoteRepository(db).get_by_id(uuid.UUID(ids["note"]))
            return {
                "analysis_status": note.analysis_status,
                "analysis_proposal_count": note.analysis_proposal_count,
                "analysis_error": note.analysis_error,
            }

    return client.portal.call(read)


def _proposals(client: TestClient, ids: dict) -> list[dict]:
    async def read() -> list[dict]:
        async with async_session_factory() as db:
            analyses = DossierAnalysisRepository(db)
            analysis = await analyses.get_current(uuid.UUID(ids["dossier"]))
            from app.repositories.analysis_proposal_repository import AnalysisProposalRepository

            rows = await AnalysisProposalRepository(analyses).list_proposals(analysis.id)
            return [
                {
                    "element_id": str(r.element_id) if r.element_id else None,
                    "kind": r.kind,
                    "definition_name": r.definition_name,
                    "value": r.proposed_value,
                    "source_type": r.source_type,
                    "source_id": str(r.source_id),
                    "proposed_by": r.proposed_by,
                    "prompt_version": r.prompt_version,
                }
                for r in rows
            ]

    return client.portal.call(read)


def _llm(monkeypatch: pytest.MonkeyPatch, updates: list[ProposedUpdate]) -> dict:
    seen: dict = {}

    async def fake(*, note: str, elements: str) -> ProposedUpdates:
        seen.update(note=note, elements=elements)
        return ProposedUpdates(updates=updates)

    monkeypatch.setattr(note_job.llm, "propose_updates_from_note", fake)
    return seen


def test_note_analysis_deposits_pending_proposals_for_the_requester(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _setup(client, "Note propose")
    seen = _llm(
        monkeypatch,
        [
            ProposedUpdate(element_id=ids["nom"], value="Dupont", reason="Le nom est bien Dupont"),
            ProposedUpdate(kind="entity", name="téléphone", value="06 12 34 56 78", reason="Son téléphone est le 06"),
        ],
    )

    client.portal.call(propose_from_note, ids["note"])

    # Le LLM reçoit la note et les éléments (avec leurs identifiants).
    assert seen["note"] == CONTENT
    assert f"id={ids['nom']}" in seen["elements"] and "Dupond" in seen["elements"]
    by_target = {p["element_id"] or p["definition_name"]: p for p in _proposals(client, ids)}
    assert by_target[ids["nom"]]["value"] == {"value": "Dupont"}
    assert by_target["téléphone"]["kind"] == AnalysisElementKind.ENTITY
    # Source, auteur et version de prompt : pour le journal et les métriques.
    for proposal in by_target.values():
        assert proposal["source_type"] == "note" and proposal["source_id"] == ids["note"]
        assert proposal["proposed_by"] == "note-agent:user-42"
        assert proposal["prompt_version"] == note_job.NOTE_PROMPT_VERSION
    note = _note(client, ids)
    assert note["analysis_status"] == "terminé" and note["analysis_proposal_count"] == 2


def test_note_analysis_with_nothing_to_propose_still_finishes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _setup(client, "Note rien")
    _llm(monkeypatch, [])

    client.portal.call(propose_from_note, ids["note"])

    assert _proposals(client, ids) == []
    note = _note(client, ids)
    assert note["analysis_status"] == "terminé" and note["analysis_proposal_count"] == 0


def test_invalid_updates_are_skipped_not_applied(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = _setup(client, "Note invalide")
    _llm(
        monkeypatch,
        [
            ProposedUpdate(element_id="inconnu", value="x", reason="r"),  # élément inexistant
            ProposedUpdate(kind="relation", name="lien", value="x", reason="r"),  # relation : non proposable
            ProposedUpdate(element_id=ids["nom"], value="  ", reason="r"),  # valeur vide
            ProposedUpdate(element_id=ids["adresse"], value="2 rue Y", reason="La note donne la nouvelle adresse"),
        ],
    )

    client.portal.call(propose_from_note, ids["note"])

    assert [p["element_id"] for p in _proposals(client, ids)] == [ids["adresse"]]
    assert _note(client, ids)["analysis_proposal_count"] == 1


def test_a_note_cannot_flood_the_user_with_proposals(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = _setup(client, "Note flood")
    many = note_job.MAX_PROPOSALS_PER_NOTE + 5
    _llm(monkeypatch, [ProposedUpdate(element_id=ids["nom"], value=f"v{i}", reason="r") for i in range(many)])

    client.portal.call(propose_from_note, ids["note"])

    assert len(_proposals(client, ids)) == note_job.MAX_PROPOSALS_PER_NOTE


def test_note_analysis_reports_a_dossier_without_analysis(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = _setup(client, "Note sans analyse", with_analysis=False)
    called = _llm(monkeypatch, [])

    client.portal.call(propose_from_note, ids["note"])

    assert called == {}  # le LLM n'est même pas appelé
    note = _note(client, ids)
    assert note["analysis_status"] == "échec" and "analyse" in note["analysis_error"]


def test_archived_note_is_not_analysed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = _setup(client, "Note archivée", archived=True)
    called = _llm(monkeypatch, [ProposedUpdate(element_id="x", value="x", reason="r")])

    client.portal.call(propose_from_note, ids["note"])

    assert called == {} and _proposals(client, ids) == []
    assert _note(client, ids)["analysis_status"] == "échec"


def test_llm_failure_is_reported_on_the_note(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = _setup(client, "Note llm en échec")

    async def boom(**kwargs: object) -> ProposedUpdates:
        raise RuntimeError("LLM indisponible")

    monkeypatch.setattr(note_job.llm, "propose_updates_from_note", boom)

    client.portal.call(propose_from_note, ids["note"])

    note = _note(client, ids)
    assert note["analysis_status"] == "échec" and note["analysis_error"] == "LLM indisponible"
    assert _proposals(client, ids) == []
