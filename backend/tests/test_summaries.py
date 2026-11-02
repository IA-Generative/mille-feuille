"""Tests pour les résumés de documents/dossiers et le hash de fichier (issue #52).

Couvre :
- Les endpoints internes de dépôt de résumé et de hash (worker → backend).
- Les endpoints publics de régénération de résumé (backend → Celery).
- Le versioning append-only : un nouveau résumé devient le "latest".
- La présence des champs summary_status / file_hash dans les réponses API.
"""

import uuid

from fastapi.testclient import TestClient

from app.db import async_session_factory
from app.models.summary import SummaryStatus
from app.repositories.dossier_repository import DossierRepository

_INTERNAL_HEADERS = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


def _create_analyse(client: TestClient, name: str = "Analyse résumés") -> str:
    return client.post("/api/analyses", json={"name": name, "description": "Test"}).json()["id"]


def _create_dossier_with_document(client: TestClient) -> tuple[str, str]:
    """Crée un dossier avec un document et retourne (dossier_id, document_id)."""
    analyse_id = _create_analyse(client)
    dossier = client.post("/api/dossiers", json={"name": "Dossier résumé", "analyse_id": analyse_id}).json()
    dossier = client.post(
        f"/api/dossiers/{dossier['id']}/documents",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
    ).json()
    return dossier["id"], dossier["documents"][0]["id"]


# ---------------------------------------------------------------------------
# Champs summary_status / file_hash dans les réponses
# ---------------------------------------------------------------------------


def test_dossier_document_has_summary_fields(client: TestClient) -> None:
    _, document_id = _create_dossier_with_document(client)

    response = client.get(f"/api/internal/documents/{document_id}", headers=_INTERNAL_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["summary_status"] == "en_attente"
    assert body["summary_error"] is None
    assert body["summary"] is None
    assert body["file_hash"] is None


def test_dossier_has_summary_fields(client: TestClient) -> None:
    analyse_id = _create_analyse(client)
    dossier = client.post(
        "/api/dossiers",
        json={"name": "Dossier champs résumé", "analyse_id": analyse_id},
    ).json()

    response = client.get(f"/api/dossiers/{dossier['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["summary_status"] == "en_attente"
    assert body["summary_error"] is None
    assert body["summary"] is None


# ---------------------------------------------------------------------------
# Hash de fichier (worker → backend)
# ---------------------------------------------------------------------------


def test_internal_set_file_hash(client: TestClient) -> None:
    _, document_id = _create_dossier_with_document(client)

    response = client.put(
        f"/api/internal/documents/{document_id}/file-hash",
        json={"file_hash": "abc123def456"},
        headers=_INTERNAL_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["file_hash"] == "abc123def456"

    # Vérifie la persistance via GET
    doc = client.get(f"/api/internal/documents/{document_id}", headers=_INTERNAL_HEADERS).json()
    assert doc["file_hash"] == "abc123def456"


def test_internal_set_file_hash_404(client: TestClient) -> None:
    response = client.put(
        f"/api/internal/documents/{uuid.uuid4()}/file-hash",
        json={"file_hash": "abc"},
        headers=_INTERNAL_HEADERS,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Statut de résumé et dépôt (versioning append-only), par le dépôt de données
# ---------------------------------------------------------------------------


def _on_app_loop(client: TestClient, work):  # noqa: ANN001, ANN202
    """Exécute `work(repository)` sur la boucle de l'application, comme le font les travaux de l'agent."""

    async def run():  # noqa: ANN202
        async with async_session_factory() as db:
            return await work(DossierRepository(db))

    return client.portal.call(run)


def test_the_status_of_a_document_summary_carries_its_error(client: TestClient) -> None:
    dossier_id, document_id = _create_dossier_with_document(client)

    async def running_then_failed(repository: DossierRepository) -> None:
        document = await repository.get_document_by_id(uuid.UUID(document_id))
        await repository.set_document_summary_status(document, SummaryStatus.EN_COURS)
        assert (await repository.get_document_by_id(uuid.UUID(document_id))).summary_status == SummaryStatus.EN_COURS
        await repository.set_document_summary_status(document, SummaryStatus.ECHEC, "LLM indisponible")

    _on_app_loop(client, running_then_failed)

    document = client.get(f"/api/dossiers/{dossier_id}").json()["documents"][0]
    assert document["summary_status"] == "échec" and document["summary_error"] == "LLM indisponible"


def test_the_status_of_a_dossier_summary(client: TestClient) -> None:
    analyse_id = _create_analyse(client)
    dossier = client.post("/api/dossiers", json={"name": "Dossier statut résumé", "analyse_id": analyse_id}).json()

    async def running(repository: DossierRepository) -> None:
        await repository.set_dossier_summary_status(
            await repository.get(uuid.UUID(dossier["id"])), SummaryStatus.EN_COURS
        )

    _on_app_loop(client, running)

    assert client.get(f"/api/dossiers/{dossier['id']}").json()["summary_status"] == "en_cours"


def test_a_new_document_summary_is_a_new_version_and_the_latest_wins(client: TestClient) -> None:
    dossier_id, document_id = _create_dossier_with_document(client)

    async def deposit_twice(repository: DossierRepository) -> tuple[uuid.UUID, uuid.UUID]:
        document = await repository.get_document_by_id(uuid.UUID(document_id))
        first = await repository.add_document_summary(document, content="Premier résumé du document.", model="gpt-4o")
        second = await repository.add_document_summary(
            document, content="Second résumé, plus récent.", model="gpt-4o-mini"
        )
        return first.id, second.id

    first_id, second_id = _on_app_loop(client, deposit_twice)

    assert first_id != second_id  # append-only : l'ancien existe toujours, le "latest" change
    document = client.get(f"/api/dossiers/{dossier_id}").json()["documents"][0]
    assert document["summary_status"] == "terminé"
    assert document["summary"]["content"] == "Second résumé, plus récent."


def test_a_dossier_summary_ends_the_generation(client: TestClient) -> None:
    analyse_id = _create_analyse(client)
    dossier = client.post("/api/dossiers", json={"name": "Dossier dépôt résumé", "analyse_id": analyse_id}).json()

    async def deposit(repository: DossierRepository) -> None:
        await repository.add_dossier_summary(
            await repository.get(uuid.UUID(dossier["id"])), content="Résumé global du dossier.", model="gpt-4o"
        )

    _on_app_loop(client, deposit)

    body = client.get(f"/api/dossiers/{dossier['id']}").json()
    assert body["summary_status"] == "terminé"
    assert body["summary"]["content"] == "Résumé global du dossier." and body["summary"]["model"] == "gpt-4o"


# ---------------------------------------------------------------------------
# Régénération de résumé (backend → Celery)
# ---------------------------------------------------------------------------


def test_regenerate_document_summary_dispatches_task(client: TestClient, monkeypatch) -> None:
    dossier_id, document_id = _create_dossier_with_document(client)

    dispatched: list[tuple] = []
    monkeypatch.setattr(
        "app.routers.dossiers.dispatch_document_summary",
        lambda d, doc: dispatched.append((d, doc)),
    )

    response = client.post(f"/api/dossiers/{dossier_id}/documents/{document_id}/summary")
    assert response.status_code == 200
    assert dispatched == [(dossier_id, document_id)]


def test_regenerate_dossier_summary_dispatches_task(client: TestClient, monkeypatch) -> None:
    analyse_id = _create_analyse(client)
    dossier = client.post(
        "/api/dossiers",
        json={"name": "Dossier régénère résumé", "analyse_id": analyse_id},
    ).json()

    dispatched: list[str] = []
    monkeypatch.setattr("app.routers.dossiers.dispatch_dossier_summary", lambda d: dispatched.append(d))

    response = client.post(f"/api/dossiers/{dossier['id']}/summary")
    assert response.status_code == 200
    assert dispatched == [dossier["id"]]


def test_regenerate_document_summary_404(client: TestClient) -> None:
    analyse_id = _create_analyse(client)
    dossier = client.post("/api/dossiers", json={"name": "Dossier 404 résumé", "analyse_id": analyse_id}).json()

    response = client.post(f"/api/dossiers/{dossier['id']}/documents/{uuid.uuid4()}/summary")
    assert response.status_code == 404
