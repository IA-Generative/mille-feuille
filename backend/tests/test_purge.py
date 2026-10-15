import uuid
from datetime import UTC, datetime, timedelta

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.connectors import s3_connector
from app.db import async_session_factory
from app.models.analyse_ephemere import AnalyseEphemere
from app.models.dossier_ephemere import DossierEphemere
from app.tasks import run_purge


@pytest.fixture(autouse=True)
def _no_real_celery_dispatch_for_purge_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("dispatch_dossier_pipeline",):
        monkeypatch.setattr(f"app.routers.ephemeral.{name}", lambda *args, **kwargs: None)


def _create_ephemeral_analyse(client: TestClient, name: str = "Analyse purge test") -> str:
    return client.post("/api/ephemeral/analyses", json={"name": name, "description": ""}).json()["analyse_id"]


def _create_and_stop_run(client: TestClient, analyse_id: str, *, persist: bool = False, finalize: bool = True) -> str:
    """`finalize=False` simule un run terminé dont la finalisation (résultat conservé + suppression du
    dossier) a échoué : le dossier terminal reste en base, c'est le filet de sécurité de la purge."""
    created = client.post(
        "/api/ephemeral/runs",
        params={"ttl_hours": 1},
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
        data={"analyse_id": analyse_id, "persist": "true" if persist else "false"},
    )
    run_id = created.json()["run_id"]
    if finalize:
        client.post(f"/api/ephemeral/runs/{run_id}/stop")
    else:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr("app.routers.ephemeral.finalize_run", _no_finalize)
            client.post(f"/api/ephemeral/runs/{run_id}/stop")
    return run_id


async def _no_finalize(*args: object, **kwargs: object) -> bool:
    return False


async def _backdate_dossier_ephemere(dossier_id: uuid.UUID) -> None:
    async with async_session_factory() as db:
        await db.execute(
            update(DossierEphemere)
            .where(DossierEphemere.dossier_id == dossier_id)
            .values(expires_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await db.commit()


async def _backdate_analyse_ephemere(analyse_id: uuid.UUID) -> None:
    async with async_session_factory() as db:
        await db.execute(
            update(AnalyseEphemere)
            .where(AnalyseEphemere.analyse_id == analyse_id)
            .values(expires_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await db.commit()


def test_purge_deletes_expired_run_including_s3_files(client: TestClient) -> None:
    analyse_id = _create_ephemeral_analyse(client)
    run_id = _create_and_stop_run(client, analyse_id, finalize=False)
    s3_key = client.get(f"/api/ephemeral/runs/{run_id}").json()["documents"][0]["s3_key"]
    client.portal.call(_backdate_dossier_ephemere, uuid.UUID(run_id))

    summary = client.portal.call(run_purge)
    assert summary["purged_dossiers"] == 1

    assert client.get(f"/api/ephemeral/runs/{run_id}").status_code == 404
    with pytest.raises(ClientError):
        s3_connector.download(s3_key)


def test_purge_does_not_delete_a_run_not_yet_expired(client: TestClient) -> None:
    analyse_id = _create_ephemeral_analyse(client)
    run_id = _create_and_stop_run(client, analyse_id, finalize=False)
    # ttl_hours=1, pas de backdate : expires_at est dans le futur.

    summary = client.portal.call(run_purge)
    assert summary["purged_dossiers"] == 0
    assert client.get(f"/api/ephemeral/runs/{run_id}").status_code == 200


def test_purge_never_deletes_a_persisted_run_even_if_backdated(client: TestClient) -> None:
    analyse_id = _create_ephemeral_analyse(client)
    run_id = _create_and_stop_run(client, analyse_id, persist=True)
    assert client.get(f"/api/ephemeral/runs/{run_id}").json()["expires_at"] is None
    # Backdate direct en DB, en contournant l'app (persist=True ne devrait
    # jamais avoir expires_at posé en pratique) : vérifie que la requête de
    # purge elle-même refuse un persist=True, pas seulement l'app.
    client.portal.call(_backdate_dossier_ephemere, uuid.UUID(run_id))

    summary = client.portal.call(run_purge)
    assert summary["purged_dossiers"] == 0
    assert client.get(f"/api/ephemeral/runs/{run_id}").status_code == 200


def test_purge_deletes_expired_analyse_without_remaining_runs(client: TestClient) -> None:
    analyse_id = _create_ephemeral_analyse(client)
    client.portal.call(_backdate_analyse_ephemere, uuid.UUID(analyse_id))

    summary = client.portal.call(run_purge)
    assert summary["purged_analyses"] == 1
    assert client.get(f"/api/ephemeral/analyses/{analyse_id}").status_code == 404


def test_purge_keeps_expired_analyse_while_a_run_still_references_it(client: TestClient) -> None:
    analyse_id = _create_ephemeral_analyse(client)
    run_id = _create_and_stop_run(client, analyse_id, finalize=False)
    client.portal.call(_backdate_analyse_ephemere, uuid.UUID(analyse_id))
    # Le run, lui, n'est pas backdaté : il reste actif et référence encore
    # l'analyse.

    summary = client.portal.call(run_purge)
    assert summary["purged_analyses"] == 0
    assert client.get(f"/api/ephemeral/analyses/{analyse_id}").status_code == 200
    assert client.get(f"/api/ephemeral/runs/{run_id}").status_code == 200


def test_purge_deletes_both_run_then_its_analyse_once_both_expired(client: TestClient) -> None:
    analyse_id = _create_ephemeral_analyse(client)
    run_id = _create_and_stop_run(client, analyse_id, finalize=False)
    client.portal.call(_backdate_dossier_ephemere, uuid.UUID(run_id))
    client.portal.call(_backdate_analyse_ephemere, uuid.UUID(analyse_id))

    summary = client.portal.call(run_purge)
    assert summary["purged_dossiers"] == 1
    assert summary["purged_analyses"] == 1
    assert client.get(f"/api/ephemeral/runs/{run_id}").status_code == 404
    assert client.get(f"/api/ephemeral/analyses/{analyse_id}").status_code == 404
