"""Les droits viennent de la base (issue #660) : Keycloak dit qui est là, pas dans quels groupes."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import factory
from app.core.security.claims import extract_identity
from app.core.security.factory import KeycloakToken, RequestContext
from app.db import async_session_factory
from app.models import AppGroupMember, AppUser
from app.repositories.access_group_repository import AccessGroupRepository
from app.services.permissions import INSTRUCTOR_ROLE_ID

ADMIN = RequestContext(user_id="admin-1", email="admin@example.org", roles=[], is_admin=True)


def test_groups_of_the_token_are_ignored() -> None:
    identity = extract_identity({"sub": "u1", "groups": ["/service-culture"], "email_verified": True}, "client")

    assert identity["groups"] == []
    assert identity["email_verified"] is True
    assert extract_identity({"sub": "u1", "email_verified": "false"}, "client")["email_verified"] is False


class _SignedIn(KeycloakToken):
    """Une session Keycloak simulée."""

    def __init__(self, user_id: str, email: str, verified: bool) -> None:
        self.identity = dict(user_id=user_id, email=email, roles=[], is_admin=False, email_verified=verified)

    def __call__(self, request) -> RequestContext:
        return RequestContext(**self.identity)


def _group_with_member(client: TestClient, email: str) -> str:
    async def create() -> str:
        async with async_session_factory() as db:
            repository = AccessGroupRepository(db)
            group = await repository.create_group(name=f"G {uuid.uuid4().hex[:8]}", description="", actor=ADMIN)
            role = await repository.get_role(INSTRUCTOR_ROLE_ID)
            await repository.add_member(group, role, email=email, actor=ADMIN)
            return str(group.id)

    return client.portal.call(create)


def _my_groups(client: TestClient, monkeypatch: pytest.MonkeyPatch, user: _SignedIn) -> list[str]:
    monkeypatch.setattr(factory, "TokenVerifier", user)
    return client.get("/api/auth/me").json()["groups"]


def test_a_reserved_place_is_linked_only_to_a_verified_address(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id, email = str(uuid.uuid4()), f"{uuid.uuid4().hex}@example.org"
    group_id = _group_with_member(client, email)

    assert _my_groups(client, monkeypatch, _SignedIn(user_id, email, verified=False)) == []
    assert _my_groups(client, monkeypatch, _SignedIn(user_id, email.upper(), verified=True)) == [group_id]


def test_removing_a_member_takes_effect_on_the_next_request(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id, email = str(uuid.uuid4()), f"{uuid.uuid4().hex}@example.org"
    group_id = _group_with_member(client, email)
    signed_in = _SignedIn(user_id, email, verified=True)
    assert _my_groups(client, monkeypatch, signed_in) == [group_id]

    async def remove() -> list[str]:
        async with async_session_factory() as db:
            member = await db.scalar(select(AppGroupMember).where(AppGroupMember.user_id == user_id))
            await AccessGroupRepository(db).remove_member(member, ADMIN)
            return (await db.get(AppUser, user_id, populate_existing=True)).groups

    assert client.portal.call(remove) == []  # la copie de l'annuaire suit, sans attendre une connexion
    assert _my_groups(client, monkeypatch, signed_in) == []
