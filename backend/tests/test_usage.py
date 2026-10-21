"""Consommation de tokens : dépôt par les workers, « ma consommation » et vue administrateur."""

import uuid

from fastapi.testclient import TestClient

from app.core.security.factory import RequestContext, get_current_user
from app.main import app

WORKER_HEADERS = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


def _deposit(client: TestClient, **fields) -> None:
    body = {"step": "classify_dossier", "model": "test-model", "input_tokens": 10, "output_tokens": 4, **fields}
    assert client.post("/api/internal/usage", json=body, headers=WORKER_HEADERS).status_code == 204


def _as(user_id: str, *, admin: bool) -> None:
    app.dependency_overrides[get_current_user] = lambda: RequestContext(
        user_id=user_id, email=f"{user_id}@example.com", roles=[], is_admin=admin
    )


def test_deposit_requires_the_worker_token(client: TestClient) -> None:
    response = client.post("/api/internal/usage", json={"step": "x", "model": "m"})
    assert response.status_code == 422  # en-tête X-App-Token absent


def test_my_usage_only_counts_my_calls(client: TestClient) -> None:
    mine, other = f"u-{uuid.uuid4()}", f"u-{uuid.uuid4()}"
    _deposit(client, user_id=mine, input_tokens=100, output_tokens=20)
    _deposit(client, user_id=mine, input_tokens=1, output_tokens=1)
    _deposit(client, user_id=other, input_tokens=999)
    _as(mine, admin=False)
    try:
        data = client.get("/api/usage/me?days=7").json()
    finally:
        del app.dependency_overrides[get_current_user]

    assert data["totals"] == {"input_tokens": 101, "output_tokens": 21, "total_tokens": 122, "calls": 2}
    assert data["by_step"][0]["step"] == "classify_dossier"
    assert data["by_model"][0]["model"] == "test-model"
    assert data["by_user"] == []


def test_admin_usage_lists_everyone_and_can_narrow_to_one_person(client: TestClient) -> None:
    person = f"u-{uuid.uuid4()}"
    _deposit(client, user_id=person, input_tokens=7, output_tokens=3)
    _deposit(client, input_tokens=5, output_tokens=5)  # sans auteur

    everyone = client.get("/api/admin/usage?days=7").json()
    narrowed = client.get(f"/api/admin/usage?days=7&user_id={person}").json()

    assert everyone["totals"]["calls"] >= 2
    assert {row["user_id"] for row in everyone["by_user"]} >= {person, None}
    assert narrowed["totals"] == {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10, "calls": 1}
    assert {row["user_id"] for row in narrowed["by_user"]} >= {person}


def test_admin_usage_is_forbidden_for_a_non_admin(client: TestClient) -> None:
    _as("regular", admin=False)
    try:
        assert client.get("/api/admin/usage").status_code == 403
    finally:
        del app.dependency_overrides[get_current_user]


def test_an_ephemeral_run_is_attributed_to_whoever_launched_it(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("app.routers.ephemeral.s3_connector.upload", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.routers.ephemeral.dispatch_dossier_pipeline", lambda *args, **kwargs: None)
    labels = '[{"name": "CNI", "definition": "Carte d\'identité"}]'
    run = client.post(
        "/api/ephemeral/classifications",
        files=[("file", ("cni.pdf", b"x", "application/pdf"))],
        data={"labels": labels},
    ).json()["run_id"]

    # Le worker ne connaît pas l'auteur : seul le dossier est donné.
    _deposit(client, dossier_id=run, input_tokens=40, output_tokens=2)

    # Le client de test est « dev-user » : le run lui revient.
    data = client.get("/api/admin/usage?days=7&user_id=dev-user").json()
    assert data["totals"]["input_tokens"] >= 40
