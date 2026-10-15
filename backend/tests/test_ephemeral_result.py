"""Fin de vie d'un run éphémère persist=false : on conserve le résultat, on supprime le reste
(dossier, fichiers S3, analyse éphémère) - voir app/services/ephemeral_run_service.py."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.connectors import s3_connector
from app.db import async_session_factory
from app.models.ephemeral_result import EphemeralResult
from app.repositories.dossier_repository import DossierRepository
from app.repositories.ephemeral_repository import EphemeralRepository
from app.tasks import run_purge

INTERNAL_HEADERS = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


@pytest.fixture(autouse=True)
def _no_real_celery_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("dispatch_dossier_pipeline",):
        monkeypatch.setattr(f"app.routers.ephemeral.{name}", lambda *args, **kwargs: None)


def _analyse(client: TestClient, *, persist: bool = False) -> str:
    response = client.post(
        "/api/ephemeral/analyses", json={"name": "Analyse résultat", "description": "", "persist": persist}
    )
    return response.json()["analyse_id"]


def _run(client: TestClient, analyse_id: str, *, persist: bool = False, ttl_hours: int = 48) -> str:
    created = client.post(
        "/api/ephemeral/runs",
        params={"ttl_hours": ttl_hours},
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
        data={"analyse_id": analyse_id, "persist": "true" if persist else "false"},
    )
    return created.json()["run_id"]


def _complete_steps(client: TestClient, run_id: str, step_status: str = "terminé") -> None:
    for step in client.get(f"/api/ephemeral/runs/{run_id}").json()["execution_steps"]:
        client.post(
            f"/api/internal/execution-steps/{step['id']}/complete",
            json={"status": step_status, "output": f"sortie {step['label']}"},
            headers=INTERNAL_HEADERS,
        )


async def _dossier_exists(run_id: uuid.UUID) -> bool:
    async with async_session_factory() as db:
        return await DossierRepository(db).get(run_id) is not None


async def _has_dossier_ephemere(run_id: uuid.UUID) -> bool:
    async with async_session_factory() as db:
        return await EphemeralRepository(db).get_dossier_ephemere(run_id) is not None


async def _backdate_result(run_id: uuid.UUID) -> None:
    async with async_session_factory() as db:
        await db.execute(
            update(EphemeralResult)
            .where(EphemeralResult.run_id == run_id)
            .values(expires_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await db.commit()


def test_finished_run_keeps_result_but_drops_dossier_files_and_analyse(client: TestClient) -> None:
    analyse_id = _analyse(client)
    run_id = _run(client, analyse_id)
    running = client.get(f"/api/ephemeral/runs/{run_id}").json()
    s3_key = running["documents"][0]["s3_key"]
    assert running["status"] == "en_cours"

    _complete_steps(client, run_id)

    result = client.get(f"/api/ephemeral/runs/{run_id}")
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "terminé"
    assert body["persist"] is False and body["ttl_hours"] == 48
    assert all(step["output"] for step in body["execution_steps"])
    assert body["documents"][0]["name"] == "cni.pdf"
    ended_at = datetime.fromisoformat(body["ended_at"])
    assert datetime.fromisoformat(body["expires_at"]) - ended_at == timedelta(hours=48)
    assert body["analyse_id"] is None  # l'analyse n'existe plus

    rid = uuid.UUID(run_id)
    assert client.portal.call(_dossier_exists, rid) is False
    assert client.portal.call(_has_dossier_ephemere, rid) is False
    assert client.get(f"/api/ephemeral/analyses/{analyse_id}").status_code == 404
    with pytest.raises(ClientError):
        s3_connector.download(s3_key)


def test_failed_run_is_finalized_too(client: TestClient) -> None:
    run_id = _run(client, _analyse(client))
    _complete_steps(client, run_id, "échec")

    body = client.get(f"/api/ephemeral/runs/{run_id}").json()
    assert body["status"] == "échec"
    assert client.portal.call(_dossier_exists, uuid.UUID(run_id)) is False


def test_stopped_run_is_finalized_and_stop_is_then_a_noop(client: TestClient) -> None:
    run_id = _run(client, _analyse(client))

    stopped = client.post(f"/api/ephemeral/runs/{run_id}/stop")
    assert stopped.status_code == 200 and stopped.json()["status"] == "arrêté"
    assert client.portal.call(_dossier_exists, uuid.UUID(run_id)) is False

    again = client.post(f"/api/ephemeral/runs/{run_id}/stop")
    assert again.status_code == 200 and again.json()["status"] == "arrêté"


def test_persist_true_run_and_analyse_are_left_intact(client: TestClient) -> None:
    analyse_id = _analyse(client, persist=True)
    run_id = _run(client, analyse_id, persist=True)
    s3_key = client.get(f"/api/ephemeral/runs/{run_id}").json()["documents"][0]["s3_key"]

    _complete_steps(client, run_id)

    body = client.get(f"/api/ephemeral/runs/{run_id}").json()
    assert body["analyse_id"] == analyse_id and body["expires_at"] is None
    assert client.portal.call(_dossier_exists, uuid.UUID(run_id)) is True
    assert client.get(f"/api/ephemeral/analyses/{analyse_id}").status_code == 200
    assert s3_connector.download(s3_key)


def test_non_persistent_run_on_a_persistent_analyse_keeps_the_analyse(client: TestClient) -> None:
    analyse_id = _analyse(client, persist=True)
    run_id = _run(client, analyse_id)

    _complete_steps(client, run_id)

    assert client.portal.call(_dossier_exists, uuid.UUID(run_id)) is False
    assert client.get(f"/api/ephemeral/runs/{run_id}").json()["analyse_id"] == analyse_id
    assert client.get(f"/api/ephemeral/analyses/{analyse_id}").status_code == 200


def test_classic_analyse_is_never_deleted(client: TestClient) -> None:
    classic = client.post("/api/analyses", json={"name": "Classique", "description": "d"}).json()["id"]
    run_id = _run(client, classic)

    _complete_steps(client, run_id)

    assert client.get(f"/api/analyses/{classic}").status_code == 200
    assert client.get(f"/api/ephemeral/runs/{run_id}").json()["status"] == "terminé"


def test_analyse_survives_until_its_last_run_finishes(client: TestClient) -> None:
    analyse_id = _analyse(client)
    first, second = _run(client, analyse_id), _run(client, analyse_id)

    _complete_steps(client, first)
    assert client.get(f"/api/ephemeral/analyses/{analyse_id}").status_code == 200  # 2e run encore actif

    _complete_steps(client, second)
    assert client.get(f"/api/ephemeral/analyses/{analyse_id}").status_code == 404
    assert client.get(f"/api/ephemeral/runs/{first}").status_code == 200
    assert client.get(f"/api/ephemeral/runs/{second}").status_code == 200


def test_result_is_scoped_to_its_creator(client: TestClient) -> None:
    token = client.post("/api/app-tokens", json={"name": "autre-compte"}).json()["token"]
    run_id = _run(client, _analyse(client))
    _complete_steps(client, run_id)

    assert client.get(f"/api/ephemeral/runs/{run_id}", headers={"X-App-Token": token}).status_code == 404
    assert client.delete(f"/api/ephemeral/runs/{run_id}", headers={"X-App-Token": token}).status_code == 404
    assert client.get(f"/api/ephemeral/runs/{run_id}").status_code == 200


def test_delete_removes_the_kept_result(client: TestClient) -> None:
    run_id = _run(client, _analyse(client))
    _complete_steps(client, run_id)

    assert client.delete(f"/api/ephemeral/runs/{run_id}").status_code == 204
    assert client.get(f"/api/ephemeral/runs/{run_id}").status_code == 404
    assert client.delete(f"/api/ephemeral/runs/{run_id}").status_code == 404


def test_purge_deletes_only_expired_results(client: TestClient) -> None:
    expired, fresh = _run(client, _analyse(client)), _run(client, _analyse(client))
    _complete_steps(client, expired)
    _complete_steps(client, fresh)
    client.portal.call(_backdate_result, uuid.UUID(expired))

    summary = client.portal.call(run_purge)

    assert summary["purged_results"] >= 1
    assert client.get(f"/api/ephemeral/runs/{expired}").status_code == 404
    assert client.get(f"/api/ephemeral/runs/{fresh}").status_code == 200


def _page_with_screenshot(client: TestClient, run_id: str, key: str, data: bytes) -> str:
    s3_connector.upload(key, data, "image/png")
    document_id = client.get(f"/api/ephemeral/runs/{run_id}").json()["documents"][0]["id"]
    page = client.post(
        f"/api/internal/documents/{document_id}/pages",
        json={"page_number": 1, "content": "Nom : Dupont", "screenshot_key": key},
        headers=INTERNAL_HEADERS,
    ).json()
    return page["id"]


def test_page_screenshot_outlives_the_run_until_the_result_is_deleted(client: TestClient) -> None:
    run_id = _run(client, _analyse(client))
    key = f"screenshots/{uuid.uuid4()}/page-1.png"
    page_id = _page_with_screenshot(client, run_id, key, b"png-bytes")

    _complete_steps(client, run_id)

    # Le dossier a disparu, pas la capture : elle se lit encore via la route du run.
    assert client.portal.call(_dossier_exists, uuid.UUID(run_id)) is False
    response = client.get(f"/api/ephemeral/runs/{run_id}/pages/{page_id}/screenshot")
    assert response.status_code == 200
    assert response.content == b"png-bytes"

    # Une page inconnue n'a pas de capture.
    assert client.get(f"/api/ephemeral/runs/{run_id}/pages/{uuid.uuid4()}/screenshot").status_code == 404

    # Supprimer le run supprime aussi sa capture.
    assert client.delete(f"/api/ephemeral/runs/{run_id}").status_code == 204
    assert client.get(f"/api/ephemeral/runs/{run_id}/pages/{page_id}/screenshot").status_code == 404
    with pytest.raises(ClientError):
        s3_connector.download(key)
