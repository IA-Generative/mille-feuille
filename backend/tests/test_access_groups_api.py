import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.core.security.factory import RequestContext, get_current_user
from app.main import app
from app.services.permissions import GROUP_ADMIN_ROLE_ID, INSTRUCTOR_ROLE_ID, READER_ROLE_ID

ADMIN_ROLE, INSTRUCTOR, READER = str(GROUP_ADMIN_ROLE_ID), str(INSTRUCTOR_ROLE_ID), str(READER_ROLE_ID)


@contextmanager
def as_person(user_id: str, *groups: str) -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: RequestContext(
        user_id=user_id, email=f"{user_id}@example.org", roles=[], is_admin=False, groups=list(groups)
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _name() -> str:
    return f"G {uuid.uuid4().hex[:8]}"


def _known_person(client: TestClient) -> str:
    user_id = str(uuid.uuid4())
    with as_person(user_id):
        client.get("/api/auth/me")
    return user_id


@pytest.fixture
def group(client: TestClient) -> str:
    return client.post("/api/groups", json={"name": _name()}).json()["id"]


def _add(client: TestClient, group_id: str, role_id: str, **identity):
    identity = identity or {"email": f"{uuid.uuid4().hex}@example.org"}
    return client.post(f"/api/groups/{group_id}/members", json={"role_id": role_id, **identity})


def test_only_super_admins_manage_groups_and_roles(client: TestClient, group: str) -> None:
    with as_person("quelquun", group):
        assert client.post("/api/groups", json={"name": _name()}).status_code == 403
        assert client.put(f"/api/groups/{group}", json={"name": _name()}).status_code == 403
        assert client.delete(f"/api/groups/{group}").status_code == 403
        assert client.post("/api/roles", json={"name": "x", "permissions": ["dossier.view"]}).status_code == 403
        assert client.delete(f"/api/roles/{READER}").status_code == 403


def test_a_group_is_hidden_from_non_members(client: TestClient, group: str) -> None:
    with as_person("etranger"):
        assert group not in [g["id"] for g in client.get("/api/groups").json()]
        assert client.get(f"/api/groups/{group}/members").status_code == 404
        assert _add(client, group, READER).status_code == 404


def test_a_member_without_the_permission_only_reads(client: TestClient, group: str) -> None:
    person = _known_person(client)
    member = _add(client, group, INSTRUCTOR, user_id=person).json()
    assert (member["pending"], member["user_id"]) == (False, person)

    with as_person(person, group):
        [mine] = client.get("/api/groups").json()
        assert (mine["id"], mine["can_manage_members"], mine["deletable"]) == (group, False, False)
        assert client.get(f"/api/groups/{group}/members").json()[0]["editable"] is False
        assert _add(client, group, READER).status_code == 403
        assert client.get(f"/api/groups/{group}/events").status_code == 403


def test_a_group_admin_manages_members_of_their_group_only(client: TestClient, group: str) -> None:
    boss = _known_person(client)
    _add(client, group, ADMIN_ROLE, user_id=boss)
    other = client.post("/api/groups", json={"name": _name()}).json()["id"]

    with as_person(boss, group):
        added = _add(client, group, INSTRUCTOR, email="Nouveau@Example.org")
        assert added.status_code == 201
        assert (added.json()["email"], added.json()["pending"]) == ("nouveau@example.org", True)
        assert _add(client, group, READER, email="nouveau@example.org").json()["detail"]["code"] == "already_member"
        member = f"/api/groups/{group}/members/{added.json()['id']}"
        assert client.patch(member, json={"role_id": READER}).json()["role_id"] == READER
        assert client.delete(member).status_code == 204
        assert _add(client, other, READER).status_code == 404
        types = [e["type"] for e in client.get(f"/api/groups/{group}/events").json()]
        assert {"member_added", "member_role_changed", "member_removed"} <= set(types)


def test_nobody_grants_or_touches_a_role_wider_than_theirs(client: TestClient, group: str) -> None:
    recruiter = client.post(
        "/api/roles", json={"name": _name(), "permissions": ["group.members", "dossier.view"]}
    ).json()["id"]
    person = _known_person(client)
    _add(client, group, recruiter, user_id=person)
    boss = _add(client, group, ADMIN_ROLE).json()

    with as_person(person, group):
        assert _add(client, group, READER).status_code == 201
        assert _add(client, group, ADMIN_ROLE).json()["detail"]["code"] == "role_too_wide"
        assert _add(client, group, INSTRUCTOR).status_code == 403
        member = f"/api/groups/{group}/members/{boss['id']}"
        assert client.patch(member, json={"role_id": READER}).status_code == 403
        assert client.delete(member).status_code == 403
        roles = client.get("/api/roles", params={"group_id": group}).json()
        assignable = {r["id"] for r in roles if r["assignable"]}
        assert READER in assignable and ADMIN_ROLE not in assignable


def test_history_deletion_rules_and_errors(client: TestClient, group: str) -> None:
    first = client.get("/api/groups/names", params={"ids": [group, "/ancien"]}).json()[0]["name"]
    renamed = client.put(f"/api/groups/{group}", json={"name": _name()}).json()
    version = next(v for v in renamed["versions"] if v["field"] == "name")
    assert client.post(f"/api/groups/{group}/restore/{version['id']}").json()["name"] == first
    assert client.post("/api/groups", json={"name": first.upper()}).status_code == 409

    member = _add(client, group, READER).json()
    assert client.delete(f"/api/groups/{group}").json()["detail"]["code"] == "group_in_use"
    assert client.delete(f"/api/roles/{READER}").json()["detail"]["code"] == "role_in_use"
    assert client.delete(f"/api/roles/{ADMIN_ROLE}").json()["detail"]["code"] == "system_role"
    client.delete(f"/api/groups/{group}/members/{member['id']}")
    assert client.delete(f"/api/groups/{group}").status_code == 204

    both = {"role_id": READER, "email": "a@example.org", "user_id": "x"}
    other = client.post("/api/groups", json={"name": _name()}).json()["id"]
    assert client.post(f"/api/groups/{other}/members", json=both).status_code == 422
    assert _add(client, other, READER, user_id="inconnu").json()["detail"]["code"] == "unknown_person"


def test_a_group_used_by_a_dossier_is_not_deleted(client: TestClient, group: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: RequestContext(
        user_id="dev-user", email="", roles=["admin"], is_admin=True, groups=[group]
    )
    try:
        analyse = client.post("/api/analyses", json={"name": "Groupe utilisé", "description": "Test"}).json()
        client.post("/api/dossiers", json={"name": "D", "analyse_id": analyse["id"]})
        assert client.delete(f"/api/groups/{group}").status_code == 409
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_the_dossier_journal_names_the_group(client: TestClient, group: str) -> None:
    name = client.get("/api/groups/names", params={"ids": [group]}).json()[0]["name"]
    app.dependency_overrides[get_current_user] = lambda: RequestContext(
        user_id="dev-user", email="", roles=["admin"], is_admin=True, groups=[group]
    )
    try:
        analyse = client.post("/api/analyses", json={"name": "Journal", "description": "Test"}).json()
        dossier = client.post("/api/dossiers", json={"name": "D", "analyse_id": analyse["id"]}).json()
        events = client.get(f"/api/dossiers/{dossier['id']}/events").json()["items"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert next(e for e in events if e["type"] == "created")["payload"]["groups"] == [name]
