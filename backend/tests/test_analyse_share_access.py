from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.core.security.factory import RequestContext, get_current_user
from app.main import app


@contextmanager
def as_user(user_id: str, *, is_admin: bool = False) -> Iterator[None]:
    """Fait agir les requêtes en tant qu'une autre personne (le client de test est « dev-user »)."""
    app.dependency_overrides[get_current_user] = lambda: RequestContext(
        user_id=user_id, email=f"{user_id}@example.com", roles=[], is_admin=is_admin, groups=["/dev-tests"]
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _create_analyse(client: TestClient) -> str:
    return client.post("/api/analyses", json={"name": "Droits de partage", "description": "Test"}).json()["id"]


def _share_by_email(client: TestClient, analyse_id: str):
    return client.post(f"/api/analyses/{analyse_id}/shares", json={"kind": "email", "email": "externe@example.com"})


@pytest.mark.parametrize("kind", ["email", "keycloak_group"])
def test_someone_else_cannot_create_a_share(client: TestClient, kind: str, without_role) -> None:
    without_role("autre")
    analyse_id = _create_analyse(client)

    with as_user("autre"):
        response = client.post(
            f"/api/analyses/{analyse_id}/shares",
            json={"kind": kind, "email": "externe@example.com", "keycloak_group": "/dev-tests"},
        )

    assert response.status_code == 403
    assert client.get(f"/api/analyses/{analyse_id}/shares").json()["total"] == 0


def test_someone_else_can_neither_list_nor_revoke_shares(client: TestClient, without_role) -> None:
    without_role("autre")
    analyse_id = _create_analyse(client)
    share = _share_by_email(client, analyse_id).json()

    with as_user("autre"):
        listed = client.get(f"/api/analyses/{analyse_id}/shares")
        revoked = client.delete(f"/api/analyses/{analyse_id}/shares/{share['id']}")

    assert listed.status_code == 403
    assert "externe@example.com" not in listed.text
    assert revoked.status_code == 403
    assert client.get(f"/api/analyses/{analyse_id}/shares").json()["total"] == 1


def test_creator_manages_shares_without_being_admin(client: TestClient) -> None:
    with as_user("auteur"):
        analyse_id = _create_analyse(client)
        created = _share_by_email(client, analyse_id)
        listed = client.get(f"/api/analyses/{analyse_id}/shares")
        revoked = client.delete(f"/api/analyses/{analyse_id}/shares/{created.json()['id']}")

    assert (created.status_code, listed.status_code, revoked.status_code) == (201, 200, 204)


def test_admin_manages_shares_of_someone_else(client: TestClient) -> None:
    with as_user("auteur"):
        analyse_id = _create_analyse(client)

    with as_user("administratrice", is_admin=True):
        assert _share_by_email(client, analyse_id).status_code == 201
