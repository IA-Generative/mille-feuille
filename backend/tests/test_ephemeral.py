from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _no_real_celery_dispatch_for_ephemeral_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Même raison que le fixture équivalent pour /api/dossiers dans
    conftest.py : app/routers/ephemeral.py importe les dispatch_* dans son
    propre namespace, le monkeypatch de dossiers.py ne les couvre pas."""
    for name in ("dispatch_dossier_pipeline",):
        monkeypatch.setattr(f"app.routers.ephemeral.{name}", lambda *args, **kwargs: None)


def _create_app_token(client: TestClient, name: str) -> str:
    return client.post("/api/app-tokens", json={"name": name}).json()["token"]


def _create_ephemeral_analyse(client: TestClient, name: str = "Analyse run test") -> str:
    return client.post("/api/ephemeral/analyses", json={"name": name, "description": ""}).json()["analyse_id"]


def test_create_and_get_ephemeral_analyse(client: TestClient) -> None:
    created = client.post(
        "/api/ephemeral/analyses",
        json={
            "name": "Analyse éphémère test",
            "description": "Test",
            "classification_prompt": "Classe le document",
            "labels": [{"name": "CNI", "definition": "Carte d'identité"}],
            "extraction_prompt": "Extrait les champs",
            "entities": [{"name": "nom", "definition": "Nom de famille", "type": "texte"}],
            "agents": [{"name": "Cohérence", "prompt": "Vérifie la cohérence"}],
        },
    )
    assert created.status_code == 201
    analyse_id = created.json()["analyse_id"]
    assert analyse_id

    fetched = client.get(f"/api/ephemeral/analyses/{analyse_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["name"] == "Analyse éphémère test"
    assert body["classification"]["prompt"] == "Classe le document"
    assert [lbl["name"] for lbl in body["classification"]["labels"]] == ["CNI"]
    assert body["extraction"]["prompt"] == "Extrait les champs"
    assert [ent["name"] for ent in body["extraction"]["entities"]] == ["nom"]
    assert [a["name"] for a in body["agents"]] == ["Cohérence"]


def test_get_unknown_ephemeral_analyse_is_404(client: TestClient) -> None:
    response = client.get("/api/ephemeral/analyses/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_classic_analyse_is_not_visible_through_ephemeral_endpoint(client: TestClient) -> None:
    classic = client.post("/api/analyses", json={"name": "Analyse classique", "description": "Test"}).json()
    response = client.get(f"/api/ephemeral/analyses/{classic['id']}")
    assert response.status_code == 404


def test_delete_ephemeral_analyse(client: TestClient) -> None:
    created = client.post("/api/ephemeral/analyses", json={"name": "À supprimer", "description": ""}).json()
    analyse_id = created["analyse_id"]

    response = client.delete(f"/api/ephemeral/analyses/{analyse_id}")
    assert response.status_code == 204

    assert client.get(f"/api/ephemeral/analyses/{analyse_id}").status_code == 404


def test_delete_ephemeral_analyse_referenced_by_a_dossier_is_409(client: TestClient) -> None:
    created = client.post("/api/ephemeral/analyses", json={"name": "Référencée", "description": ""}).json()
    analyse_id = created["analyse_id"]

    client.post("/api/dossiers", json={"name": "Dossier lié", "analyse_id": analyse_id})

    response = client.delete(f"/api/ephemeral/analyses/{analyse_id}")
    assert response.status_code == 409


def test_ephemeral_analyse_is_scoped_to_its_creator(client: TestClient) -> None:
    token_a = _create_app_token(client, "app-a")
    token_b = _create_app_token(client, "app-b")

    created = client.post(
        "/api/ephemeral/analyses",
        json={"name": "Analyse app A", "description": ""},
        headers={"X-App-Token": token_a},
    ).json()
    analyse_id = created["analyse_id"]

    # Visible pour son créateur (le même token API)...
    assert client.get(f"/api/ephemeral/analyses/{analyse_id}", headers={"X-App-Token": token_a}).status_code == 200
    # ... mais pas pour un autre token API, ni pour une session Keycloak (dev-user en test).
    assert client.get(f"/api/ephemeral/analyses/{analyse_id}", headers={"X-App-Token": token_b}).status_code == 404
    assert client.get(f"/api/ephemeral/analyses/{analyse_id}").status_code == 404


def test_invalid_app_token_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/ephemeral/analyses",
        json={"name": "X", "description": ""},
        headers={"X-App-Token": "not-a-real-token"},
    )
    assert response.status_code == 401


def test_create_run_flux_a_launches_pipeline_immediately(client: TestClient) -> None:
    analyse_id = _create_ephemeral_analyse(client)

    created = client.post(
        f"/api/ephemeral/analyses/{analyse_id}/runs",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
        data={"persist": "false"},
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]
    assert run_id

    run = client.get(f"/api/ephemeral/runs/{run_id}").json()
    assert run["analyse_id"] == analyse_id
    assert run["status"] == "en_cours"
    assert run["started_at"] is not None
    assert len(run["documents"]) == 1
    kinds = {step["kind"] for step in run["execution_steps"]}
    assert kinds == {"classification", "extraction"}


def test_create_run_flux_b_in_one_call(client: TestClient) -> None:
    analyse_id = _create_ephemeral_analyse(client)

    created = client.post(
        "/api/ephemeral/runs",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
        data={"analyse_id": analyse_id, "persist": "false"},
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]

    run = client.get(f"/api/ephemeral/runs/{run_id}").json()
    assert run["analyse_id"] == analyse_id
    assert run["status"] == "en_cours"


def test_run_against_a_classic_analyse(client: TestClient) -> None:
    classic_analyse_id = client.post(
        "/api/analyses", json={"name": "Analyse classique run", "description": "Test"}
    ).json()["id"]

    created = client.post(
        "/api/ephemeral/runs",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
        data={"analyse_id": classic_analyse_id},
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]

    run = client.get(f"/api/ephemeral/runs/{run_id}").json()
    assert run["analyse_id"] == classic_analyse_id


def test_run_with_unknown_analyse_id_is_404(client: TestClient) -> None:
    response = client.post(
        "/api/ephemeral/runs",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
        data={"analyse_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404


def test_run_ttl_hours_validation(client: TestClient) -> None:
    analyse_id = _create_ephemeral_analyse(client)

    too_high = client.post(
        "/api/ephemeral/runs",
        params={"ttl_hours": 999999},
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
        data={"analyse_id": analyse_id},
    )
    assert too_high.status_code == 400

    zero = client.post(
        "/api/ephemeral/runs",
        params={"ttl_hours": 0},
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
        data={"analyse_id": analyse_id},
    )
    assert zero.status_code == 400

    ok = client.post(
        "/api/ephemeral/runs",
        params={"ttl_hours": 48},
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
        data={"analyse_id": analyse_id},
    )
    assert ok.status_code == 201


def test_get_unknown_run_is_404(client: TestClient) -> None:
    response = client.get("/api/ephemeral/runs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_run_is_scoped_to_its_creator(client: TestClient) -> None:
    token_a = _create_app_token(client, "run-app-a")
    token_b = _create_app_token(client, "run-app-b")
    analyse_id = _create_ephemeral_analyse(client)

    created = client.post(
        "/api/ephemeral/runs",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
        data={"analyse_id": analyse_id},
        headers={"X-App-Token": token_a},
    )
    run_id = created.json()["run_id"]

    assert client.get(f"/api/ephemeral/runs/{run_id}", headers={"X-App-Token": token_a}).status_code == 200
    assert client.get(f"/api/ephemeral/runs/{run_id}", headers={"X-App-Token": token_b}).status_code == 404
    assert client.get(f"/api/ephemeral/runs/{run_id}").status_code == 404


def _create_run(client: TestClient, analyse_id: str) -> str:
    created = client.post(
        "/api/ephemeral/runs",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
        data={"analyse_id": analyse_id},
    )
    return created.json()["run_id"]


def test_stop_ephemeral_run(client: TestClient) -> None:
    run_id = _create_run(client, _create_ephemeral_analyse(client))
    assert client.get(f"/api/ephemeral/runs/{run_id}").json()["status"] == "en_cours"

    stopped = client.post(f"/api/ephemeral/runs/{run_id}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "arrêté"
    assert stopped.json()["ended_at"] is not None


def test_stop_is_noop_once_already_stopped(client: TestClient) -> None:
    run_id = _create_run(client, _create_ephemeral_analyse(client))
    client.post(f"/api/ephemeral/runs/{run_id}/stop")
    second = client.post(f"/api/ephemeral/runs/{run_id}/stop")
    assert second.status_code == 200
    assert second.json()["status"] == "arrêté"


def test_stop_unknown_run_is_404(client: TestClient) -> None:
    response = client.post("/api/ephemeral/runs/00000000-0000-0000-0000-000000000000/stop")
    assert response.status_code == 404


def test_delete_running_ephemeral_run_stops_then_deletes(client: TestClient) -> None:
    run_id = _create_run(client, _create_ephemeral_analyse(client))

    response = client.delete(f"/api/ephemeral/runs/{run_id}")
    assert response.status_code == 204
    assert client.get(f"/api/ephemeral/runs/{run_id}").status_code == 404


def test_delete_already_stopped_ephemeral_run(client: TestClient) -> None:
    run_id = _create_run(client, _create_ephemeral_analyse(client))
    client.post(f"/api/ephemeral/runs/{run_id}/stop")

    response = client.delete(f"/api/ephemeral/runs/{run_id}")
    assert response.status_code == 204
    assert client.get(f"/api/ephemeral/runs/{run_id}").status_code == 404


def test_delete_unknown_run_is_404(client: TestClient) -> None:
    response = client.delete("/api/ephemeral/runs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_delete_ephemeral_run_removes_s3_files(client: TestClient) -> None:
    from botocore.exceptions import ClientError

    from app.connectors import s3_connector

    analyse_id = _create_ephemeral_analyse(client)
    run_id = _create_run(client, analyse_id)
    s3_key = client.get(f"/api/ephemeral/runs/{run_id}").json()["documents"][0]["s3_key"]

    client.delete(f"/api/ephemeral/runs/{run_id}")

    with pytest.raises(ClientError):
        s3_connector.download(s3_key)


def test_delete_run_is_scoped_to_its_creator(client: TestClient) -> None:
    token_a = _create_app_token(client, "delete-app-a")
    token_b = _create_app_token(client, "delete-app-b")
    analyse_id = _create_ephemeral_analyse(client)

    created = client.post(
        "/api/ephemeral/runs",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
        data={"analyse_id": analyse_id},
        headers={"X-App-Token": token_a},
    )
    run_id = created.json()["run_id"]

    assert client.delete(f"/api/ephemeral/runs/{run_id}", headers={"X-App-Token": token_b}).status_code == 404
    assert client.delete(f"/api/ephemeral/runs/{run_id}", headers={"X-App-Token": token_a}).status_code == 204


INTERNAL_HEADERS = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


def _complete_all_steps(client: TestClient, run_id: str, step_status: str = "terminé") -> None:
    steps = client.get(f"/api/ephemeral/runs/{run_id}").json()["execution_steps"]
    for step in steps:
        client.post(
            f"/api/internal/execution-steps/{step['id']}/complete",
            json={"status": step_status, "output": "ok"},
            headers=INTERNAL_HEADERS,
        )


def test_run_expires_at_is_null_while_running(client: TestClient) -> None:
    run_id = _create_run(client, _create_ephemeral_analyse(client))
    run = client.get(f"/api/ephemeral/runs/{run_id}").json()
    assert run["status"] == "en_cours"
    assert run["expires_at"] is None


def test_run_expires_at_set_on_successful_completion(client: TestClient) -> None:
    analyse_id = _create_ephemeral_analyse(client)
    created = client.post(
        "/api/ephemeral/runs",
        params={"ttl_hours": 48},
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
        data={"analyse_id": analyse_id},
    )
    run_id = created.json()["run_id"]

    _complete_all_steps(client, run_id, "terminé")

    run = client.get(f"/api/ephemeral/runs/{run_id}").json()
    assert run["status"] == "terminé"
    assert run["ended_at"] is not None
    assert run["expires_at"] is not None

    ended_at = datetime.fromisoformat(run["ended_at"])
    expires_at = datetime.fromisoformat(run["expires_at"])
    assert expires_at - ended_at == timedelta(hours=48)


def test_run_status_is_echec_when_a_step_fails(client: TestClient) -> None:
    run_id = _create_run(client, _create_ephemeral_analyse(client))
    _complete_all_steps(client, run_id, "échec")

    run = client.get(f"/api/ephemeral/runs/{run_id}").json()
    assert run["status"] == "échec"
    assert run["expires_at"] is not None


def test_run_expires_at_set_on_manual_stop(client: TestClient) -> None:
    analyse_id = _create_ephemeral_analyse(client)
    created = client.post(
        "/api/ephemeral/runs",
        params={"ttl_hours": 1},
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
        data={"analyse_id": analyse_id},
    )
    run_id = created.json()["run_id"]

    stopped = client.post(f"/api/ephemeral/runs/{run_id}/stop").json()
    assert stopped["status"] == "arrêté"
    assert stopped["expires_at"] is not None


def test_run_expires_at_stays_null_when_persist_true(client: TestClient) -> None:
    analyse_id = _create_ephemeral_analyse(client)
    created = client.post(
        "/api/ephemeral/runs",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
        data={"analyse_id": analyse_id, "persist": "true"},
    )
    run_id = created.json()["run_id"]

    stopped = client.post(f"/api/ephemeral/runs/{run_id}/stop").json()
    assert stopped["status"] == "arrêté"
    assert stopped["persist"] is True
    assert stopped["expires_at"] is None


def test_analyse_ephemere_is_deleted_once_its_run_is_finished(client: TestClient) -> None:
    analyse_id = _create_ephemeral_analyse(client)
    assert client.get(f"/api/ephemeral/analyses/{analyse_id}").json()["expires_at"] is None

    run_id = _create_run(client, analyse_id)
    client.post(f"/api/ephemeral/runs/{run_id}/stop")

    assert client.get(f"/api/ephemeral/analyses/{analyse_id}").status_code == 404
    # Le résultat, lui, reste consultable (voir tests/test_ephemeral_result.py).
    assert client.get(f"/api/ephemeral/runs/{run_id}").json()["analyse_id"] is None


def _as_other_keycloak_user():
    from app.core.security.factory import RequestContext

    return RequestContext(user_id="other-keycloak-user", email="other@example.com", roles=[], is_admin=False)


def test_ephemeral_analyse_is_scoped_per_keycloak_user(client: TestClient) -> None:
    """Même vérification que test_ephemeral_analyse_is_scoped_to_its_creator
    mais côté Keycloak (dev-user en test) plutôt que token API : deux
    identités Keycloak différentes ne doivent pas se voir non plus."""
    from app.core.security.factory import get_current_user
    from app.main import app

    analyse_id = _create_ephemeral_analyse(client, "Analyse dev-user")

    app.dependency_overrides[get_current_user] = _as_other_keycloak_user
    try:
        assert client.get(f"/api/ephemeral/analyses/{analyse_id}").status_code == 404
        assert client.delete(f"/api/ephemeral/analyses/{analyse_id}").status_code == 404
    finally:
        del app.dependency_overrides[get_current_user]

    # Le propriétaire d'origine (dev-user, sans override) y a toujours accès.
    assert client.get(f"/api/ephemeral/analyses/{analyse_id}").status_code == 200


def test_ephemeral_run_is_scoped_per_keycloak_user(client: TestClient) -> None:
    from app.core.security.factory import get_current_user
    from app.main import app

    run_id = _create_run(client, _create_ephemeral_analyse(client, "Analyse run dev-user"))

    app.dependency_overrides[get_current_user] = _as_other_keycloak_user
    try:
        assert client.get(f"/api/ephemeral/runs/{run_id}").status_code == 404
        assert client.post(f"/api/ephemeral/runs/{run_id}/stop").status_code == 404
        assert client.delete(f"/api/ephemeral/runs/{run_id}").status_code == 404
    finally:
        del app.dependency_overrides[get_current_user]

    assert client.get(f"/api/ephemeral/runs/{run_id}").status_code == 200


def test_ephemeral_analyse_created_via_app_token_is_not_visible_to_keycloak_user(client: TestClient) -> None:
    """Pas de visibilité croisée entre les deux mécanismes d'auth (voir
    docs/ephemeral-api.md, section Visibilité)."""
    token = _create_app_token(client, "app-token-owner")
    created = client.post(
        "/api/ephemeral/analyses",
        json={"name": "Analyse via token", "description": ""},
        headers={"X-App-Token": token},
    ).json()

    # Session Keycloak (dev-user en test), sans le jeton API du créateur.
    assert client.get(f"/api/ephemeral/analyses/{created['analyse_id']}").status_code == 404
