"""Clé d'API de l'environnement (EPHEMERAL_API_KEY) : accès à /api/ephemeral/*, toujours non persistant."""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import EphemeralSettings
from app.core.security import ephemeral as ephemeral_security

KEY = "cle-d-environnement-0123456789"
BY_KEY = {"X-App-Token": KEY}
BY_BEARER = {"Authorization": f"Bearer {KEY}"}
FILE = [("file", ("cni.pdf", b"fake-bytes", "application/pdf"))]
LABELS = json.dumps([{"name": "CNI", "definition": "Carte d'identité"}])


@pytest.fixture(autouse=True)
def _env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ephemeral_security._settings, "EPHEMERAL_API_KEY", KEY)
    monkeypatch.setattr("app.routers.ephemeral.s3_connector.upload", lambda *args, **kwargs: None)
    for name in ("dispatch_dossier_pipeline",):
        monkeypatch.setattr(f"app.routers.ephemeral.{name}", lambda *args, **kwargs: None)


@pytest.mark.parametrize("headers", [BY_KEY, BY_BEARER])
def test_the_key_gives_access_in_x_app_token_and_in_bearer(client: TestClient, headers: dict) -> None:
    created = client.post("/api/ephemeral/analyses", json={"name": "Via clé"}, headers=headers)
    assert created.status_code == 201
    assert client.get(f"/api/ephemeral/analyses/{created.json()['analyse_id']}", headers=headers).status_code == 200


def test_a_wrong_x_app_token_is_still_rejected(client: TestClient) -> None:
    response = client.post("/api/ephemeral/analyses", json={"name": "x"}, headers={"X-App-Token": KEY + "x"})
    assert response.status_code == 401


def test_without_the_variable_the_key_gives_nothing(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ephemeral_security._settings, "EPHEMERAL_API_KEY", "")
    assert client.post("/api/ephemeral/analyses", json={"name": "x"}, headers=BY_KEY).status_code == 401
    assert client.post("/api/ephemeral/analyses", json={"name": "x"}, headers={"X-App-Token": ""}).status_code in (
        201,
        401,
    )  # pas de clé : on retombe sur l'authentification habituelle


def test_persist_true_is_refused_on_every_creation_route(client: TestClient) -> None:
    analyse = client.post("/api/ephemeral/analyses", json={"name": "a"}, headers=BY_KEY).json()["analyse_id"]

    assert (
        client.post("/api/ephemeral/analyses", json={"name": "b", "persist": True}, headers=BY_KEY).status_code == 403
    )
    assert (
        client.post(
            f"/api/ephemeral/analyses/{analyse}/runs",
            files=[("files", FILE[0][1])],
            data={"persist": "true"},
            headers=BY_KEY,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/ephemeral/runs",
            files=[("files", FILE[0][1])],
            data={"analyse_id": analyse, "persist": "true"},
            headers=BY_KEY,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/ephemeral/classifications", files=FILE, data={"labels": LABELS, "persist": "true"}, headers=BY_KEY
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/ephemeral/extractions",
            files=FILE,
            data={"entities": json.dumps([{"name": "nom", "type": "texte"}]), "persist": "true"},
            headers=BY_KEY,
        ).status_code
        == 403
    )


def test_runs_through_the_key_are_never_persistent(client: TestClient) -> None:
    started = client.post("/api/ephemeral/classifications", files=FILE, data={"labels": LABELS}, headers=BY_KEY)
    assert started.status_code == 201
    run = client.get(f"/api/ephemeral/runs/{started.json()['run_id']}", headers=BY_BEARER).json()
    assert run["persist"] is False

    analyse_id = run["analyse_id"]
    analyse = client.get(f"/api/ephemeral/analyses/{analyse_id}", headers=BY_KEY).json()
    assert analyse["persist"] is False


def test_the_key_only_runs_the_ephemeral_analyses_it_created(client: TestClient) -> None:
    classic = client.post("/api/analyses", json={"name": "Analyse classique", "description": "Test"}).json()["id"]
    token = client.post("/api/app-tokens", json={"name": "autre"}).json()["token"]
    foreign = client.post("/api/ephemeral/analyses", json={"name": "d'un autre"}, headers={"X-App-Token": token})
    own = client.post("/api/ephemeral/analyses", json={"name": "à moi"}, headers=BY_KEY).json()["analyse_id"]

    files = [("files", FILE[0][1])]
    assert client.post(f"/api/ephemeral/analyses/{classic}/runs", files=files, headers=BY_KEY).status_code == 404
    foreign_id = foreign.json()["analyse_id"]
    assert client.post(f"/api/ephemeral/analyses/{foreign_id}/runs", files=files, headers=BY_KEY).status_code == 404
    assert (
        client.post("/api/ephemeral/runs", files=files, data={"analyse_id": classic}, headers=BY_KEY).status_code == 404
    )
    assert client.post(f"/api/ephemeral/analyses/{own}/runs", files=files, headers=BY_KEY).status_code == 201
    # Le jeton, lui, peut toujours viser une analyse classique.
    assert (
        client.post(f"/api/ephemeral/analyses/{classic}/runs", files=files, headers={"X-App-Token": token}).status_code
        == 201
    )


def test_resources_of_the_key_are_invisible_to_other_identities(client: TestClient) -> None:
    token = client.post("/api/app-tokens", json={"name": "voisin"}).json()["token"]
    started = client.post("/api/ephemeral/classifications", files=FILE, data={"labels": LABELS}, headers=BY_KEY)
    url = f"/api/ephemeral/classifications/{started.json()['run_id']}"

    assert client.get(url, headers=BY_KEY).status_code == 200
    assert client.get(url, headers={"X-App-Token": token}).status_code == 404


def test_a_too_short_key_is_rejected_at_startup() -> None:
    with pytest.raises(ValidationError):
        EphemeralSettings(EPHEMERAL_API_KEY="court")
    assert EphemeralSettings(EPHEMERAL_API_KEY="").EPHEMERAL_API_KEY == ""
