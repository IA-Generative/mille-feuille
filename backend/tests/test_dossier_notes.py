"""Tests des notes internes d'un dossier (issue #117)."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db import async_session_factory
from app.models.dossier_analysis import DossierAnalysis, DossierAnalysisStatus
from app.repositories.dossier_note_repository import DossierNoteRepository


@pytest.fixture
def dispatched(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Remplace le dépôt de la tâche d'analyse : rien n'est envoyé au worker."""
    calls: list[str] = []
    monkeypatch.setattr("app.routers.dossier_notes.dispatch_note_proposals", lambda note_id: calls.append(note_id))
    monkeypatch.setattr("app.routers.dossiers.dispatch_classification", lambda d: None)
    monkeypatch.setattr("app.routers.dossiers.dispatch_entity_extraction", lambda d: None)
    monkeypatch.setattr("app.routers.dossiers.dispatch_agent_execution", lambda *args, **kwargs: None)
    return calls


def _dossier(client: TestClient, name: str = "Dossier notes") -> str:
    analyse_id = client.post("/api/analyses", json={"name": "Analyse notes", "description": "t"}).json()["id"]
    return client.post("/api/dossiers", json={"name": name, "analyse_id": analyse_id}).json()["id"]


def _note(client: TestClient, dossier_id: str, content: str = "Pièce vérifiée par téléphone") -> dict[str, Any]:
    response = client.post(f"/api/dossiers/{dossier_id}/notes", json={"content": content})
    assert response.status_code == 201
    return response.json()


def _url(dossier_id: str, note_id: str, suffix: str = "") -> str:
    return f"/api/dossiers/{dossier_id}/notes/{note_id}{suffix}"


# --- Créer, lister ---


def test_create_and_list_notes(client: TestClient) -> None:
    dossier_id = _dossier(client)
    note = _note(client, dossier_id, "  Première note  ")

    assert note["content"] == "Première note"
    assert note["version_number"] == 1
    assert note["created_by"] and note["last_author_id"] == note["created_by"]
    assert note["archived"] is False
    assert note["analysis_status"] is None

    second = _note(client, dossier_id, "Deuxième note")
    listed = client.get(f"/api/dossiers/{dossier_id}/notes").json()
    # La plus récente d'abord.
    assert [n["id"] for n in listed] == [second["id"], note["id"]]


def test_note_content_is_required_and_bounded(client: TestClient) -> None:
    dossier_id = _dossier(client)
    url = f"/api/dossiers/{dossier_id}/notes"
    assert client.post(url, json={"content": ""}).status_code == 422
    assert client.post(url, json={}).status_code == 422
    assert client.post(url, json={"content": "x" * 20001}).status_code == 422


def test_notes_of_an_unknown_dossier_are_404(client: TestClient) -> None:
    unknown = uuid.uuid4()
    assert client.get(f"/api/dossiers/{unknown}/notes").status_code == 404
    assert client.post(f"/api/dossiers/{unknown}/notes", json={"content": "x"}).status_code == 404


def test_a_note_of_another_dossier_is_not_reachable(client: TestClient) -> None:
    note = _note(client, _dossier(client, "A"))
    other = _dossier(client, "B")
    assert client.get(_url(other, note["id"], "/versions")).status_code == 404
    assert client.put(_url(other, note["id"]), json={"content": "x"}).status_code == 404
    assert client.post(_url(other, note["id"], "/archive")).status_code == 404
    assert client.get(f"/api/dossiers/{other}/notes").json() == []


# --- Versions et restauration ---


def test_editing_adds_a_version_and_keeps_the_history(client: TestClient) -> None:
    dossier_id = _dossier(client)
    note = _note(client, dossier_id, "Version un")

    updated = client.put(_url(dossier_id, note["id"]), json={"content": "Version deux"}).json()
    assert updated["content"] == "Version deux"
    assert updated["version_number"] == 2

    versions = client.get(_url(dossier_id, note["id"], "/versions")).json()
    assert [(v["version_number"], v["content"]) for v in versions] == [(1, "Version un"), (2, "Version deux")]
    assert all(v["author_id"] for v in versions)
    assert versions[0]["restored_from_version_id"] is None


def test_restoring_adds_a_version_and_deletes_nothing(client: TestClient) -> None:
    dossier_id = _dossier(client)
    note = _note(client, dossier_id, "Version un")
    client.put(_url(dossier_id, note["id"]), json={"content": "Version deux"})
    first = client.get(_url(dossier_id, note["id"], "/versions")).json()[0]

    restored = client.post(_url(dossier_id, note["id"], "/restore"), json={"version_id": first["id"]})

    assert restored.status_code == 200
    assert restored.json()["content"] == "Version un"
    assert restored.json()["version_number"] == 3
    versions = client.get(_url(dossier_id, note["id"], "/versions")).json()
    assert [v["version_number"] for v in versions] == [1, 2, 3]
    assert versions[2]["restored_from_version_id"] == first["id"]
    assert [v["content"] for v in versions][:2] == ["Version un", "Version deux"]


def test_restoring_an_unknown_or_foreign_version_is_404(client: TestClient) -> None:
    dossier_id = _dossier(client)
    note = _note(client, dossier_id)
    other = _note(client, dossier_id, "Autre")
    foreign = client.get(_url(dossier_id, other["id"], "/versions")).json()[0]
    assert (
        client.post(_url(dossier_id, note["id"], "/restore"), json={"version_id": str(uuid.uuid4())}).status_code == 404
    )
    assert client.post(_url(dossier_id, note["id"], "/restore"), json={"version_id": foreign["id"]}).status_code == 404


# --- Archiver ---


def test_archiving_hides_the_note_but_keeps_its_history(client: TestClient) -> None:
    dossier_id = _dossier(client)
    note = _note(client, dossier_id, "À archiver")
    client.put(_url(dossier_id, note["id"]), json={"content": "Modifiée"})

    archived = client.post(_url(dossier_id, note["id"], "/archive")).json()
    assert archived["archived"] is True
    assert client.get(f"/api/dossiers/{dossier_id}/notes").json() == []
    shown = client.get(f"/api/dossiers/{dossier_id}/notes", params={"include_archived": True}).json()
    assert [n["id"] for n in shown] == [note["id"]]
    assert len(client.get(_url(dossier_id, note["id"], "/versions")).json()) == 2

    restored = client.post(_url(dossier_id, note["id"], "/unarchive")).json()
    assert restored["archived"] is False
    assert [n["id"] for n in client.get(f"/api/dossiers/{dossier_id}/notes").json()] == [note["id"]]


def test_an_archived_note_cannot_be_edited_or_restored(client: TestClient) -> None:
    dossier_id = _dossier(client)
    note = _note(client, dossier_id)
    version = client.get(_url(dossier_id, note["id"], "/versions")).json()[0]
    client.post(_url(dossier_id, note["id"], "/archive"))

    assert client.put(_url(dossier_id, note["id"]), json={"content": "x"}).status_code == 409
    assert client.post(_url(dossier_id, note["id"], "/restore"), json={"version_id": version["id"]}).status_code == 409


# --- Analyse d'une note, sur demande (propositions) ---


def _launch(client: TestClient, dossier_id: str) -> None:
    client.post(f"/api/dossiers/{dossier_id}/launch")


def test_adding_or_editing_a_note_never_triggers_the_analysis(client: TestClient, dispatched: list[str]) -> None:
    dossier_id = _dossier(client)
    _launch(client, dossier_id)
    note = _note(client, dossier_id)
    client.put(_url(dossier_id, note["id"]), json={"content": "Modifiée"})
    assert dispatched == []
    assert client.get(f"/api/dossiers/{dossier_id}/notes").json()[0]["analysis_status"] is None


def test_asking_for_proposals_dispatches_the_analysis_and_tracks_it(client: TestClient, dispatched: list[str]) -> None:
    dossier_id = _dossier(client)
    _launch(client, dossier_id)
    note = _note(client, dossier_id)
    client.put(_url(dossier_id, note["id"]), json={"content": "Version deux"})

    response = client.post(_url(dossier_id, note["id"], "/propose"))

    assert response.status_code == 202
    body = response.json()
    assert body["analysis_status"] == "en_cours"
    assert body["analysis_version_number"] == 2  # la version actuelle de la note
    assert dispatched == [note["id"]]


def test_a_note_cannot_be_analysed_twice_at_once(client: TestClient, dispatched: list[str]) -> None:
    dossier_id = _dossier(client)
    _launch(client, dossier_id)
    note = _note(client, dossier_id)
    assert client.post(_url(dossier_id, note["id"], "/propose")).status_code == 202
    assert client.post(_url(dossier_id, note["id"], "/propose")).status_code == 409
    assert dispatched == [note["id"]]


def test_proposals_need_an_analysis_a_live_note_and_an_unfrozen_analysis(
    client: TestClient, dispatched: list[str]
) -> None:
    dossier_id = _dossier(client)  # jamais lancé : pas d'analyse
    note = _note(client, dossier_id)
    assert client.post(_url(dossier_id, note["id"], "/propose")).status_code == 404

    _launch(client, dossier_id)
    client.post(_url(dossier_id, note["id"], "/archive"))
    assert client.post(_url(dossier_id, note["id"], "/propose")).status_code == 409
    client.post(_url(dossier_id, note["id"], "/unarchive"))

    analysis_id = client.get(f"/api/dossiers/{dossier_id}/analyse-dossier").json()["id"]

    async def freeze() -> None:
        async with async_session_factory() as session:
            row = await session.get(DossierAnalysis, uuid.UUID(analysis_id))
            row.status = DossierAnalysisStatus.FIGEE
            await session.commit()

    client.portal.call(freeze)
    assert client.post(_url(dossier_id, note["id"], "/propose")).status_code == 409
    assert dispatched == []


# --- Ce que l'agent lit et dépose (dépôt de données) ---


def _notes(client: TestClient, work):  # noqa: ANN001, ANN202
    """Exécute `work(repository)` sur la boucle de l'application, comme le font les travaux de l'agent."""

    async def run_work():  # noqa: ANN202
        async with async_session_factory() as session:
            return await work(DossierNoteRepository(session))

    return client.portal.call(run_work)


def test_the_agent_lists_only_live_notes_with_their_current_content(client: TestClient, dispatched: list[str]) -> None:
    dossier_id = _dossier(client)
    kept = _note(client, dossier_id, "Gardée")
    gone = _note(client, dossier_id, "Archivée")
    client.put(_url(dossier_id, kept["id"]), json={"content": "Gardée (modifiée)"})
    client.post(_url(dossier_id, gone["id"], "/archive"))

    async def read(repository: DossierNoteRepository) -> list[tuple]:
        notes = await repository.list(uuid.UUID(dossier_id))
        return [(str(n.id), n.current.content, n.current.version_number) for n in notes]

    assert _notes(client, read) == [(kept["id"], "Gardée (modifiée)", 2)]


def test_a_note_written_by_the_chat_is_attributed_to_it(client: TestClient) -> None:
    dossier_id = _dossier(client)

    async def write(repository: DossierNoteRepository) -> tuple[str, int]:
        note = await repository.create(uuid.UUID(dossier_id), content="Appel de l'avocat", user_id="chat-agent:u1")
        return str(note.id), note.current.version_number

    note_id, version = _notes(client, write)

    assert version == 1
    [note] = [n for n in client.get(f"/api/dossiers/{dossier_id}/notes").json() if n["id"] == note_id]
    assert (note["content"], note["created_by"], note["last_author_id"]) == (
        "Appel de l'avocat",
        "chat-agent:u1",
        "chat-agent:u1",
    )


def test_the_note_the_agent_analyses_knows_who_asked(client: TestClient, dispatched: list[str]) -> None:
    dossier_id = _dossier(client)
    _launch(client, dossier_id)
    note = _note(client, dossier_id)
    client.post(_url(dossier_id, note["id"], "/propose"))

    async def read(repository: DossierNoteRepository) -> tuple:
        row = await repository.get_by_id(uuid.UUID(note["id"]))
        return row.current.content, str(row.dossier_id), row.analysis_requested_by

    content, noted_dossier, requested_by = _notes(client, read)

    assert content == note["content"] and noted_dossier == dossier_id and requested_by == note["created_by"]


def test_the_end_of_the_analysis_is_reported_on_the_note(client: TestClient, dispatched: list[str]) -> None:
    dossier_id = _dossier(client)
    _launch(client, dossier_id)
    note = _note(client, dossier_id)
    client.post(_url(dossier_id, note["id"], "/propose"))

    async def finish(repository: DossierNoteRepository, **result: object) -> None:
        await repository.finish_analysis(await repository.get_by_id(uuid.UUID(note["id"])), **result)

    _notes(client, lambda r: finish(r, status="terminé", proposal_count=3, error=None))
    shown = client.get(f"/api/dossiers/{dossier_id}/notes").json()[0]
    assert (shown["analysis_status"], shown["analysis_proposal_count"], shown["analysis_error"]) == ("terminé", 3, None)
    # Une nouvelle analyse est possible une fois la précédente terminée.
    assert client.post(_url(dossier_id, note["id"], "/propose")).status_code == 202

    _notes(client, lambda r: finish(r, status="échec", proposal_count=None, error="LLM indisponible"))
    shown = client.get(f"/api/dossiers/{dossier_id}/notes").json()[0]
    assert (shown["analysis_status"], shown["analysis_error"]) == ("échec", "LLM indisponible")
