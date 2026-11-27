"""Les rôles appliqués (#664), avec les vraies règles."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.core.security.factory import RequestContext, get_current_user
from app.main import app
from app.services import required_permission
from app.services.permissions import GROUP_ADMIN_ROLE_ID, INSTRUCTOR_ROLE_ID, READER_ROLE_ID, Permission


@pytest.fixture(autouse=True)
def open_analyses() -> None:
    """Remplace le préalable de conftest.py : ici, les vraies règles."""


@contextmanager
def signed_in(user_id: str, *groups: str, is_admin: bool = False) -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: RequestContext(
        user_id=user_id, email=f"{user_id}@example.org", roles=[], is_admin=is_admin, groups=list(groups)
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def world(client: TestClient) -> dict:
    """Un groupe, une personne par rôle fourni, une analyse et un dossier restreint de ce groupe."""
    group = client.post("/api/groups", json={"name": f"G {uuid.uuid4().hex[:8]}"}).json()["id"]
    people = {}
    for name, role in (("reader", READER_ROLE_ID), ("instructor", INSTRUCTOR_ROLE_ID), ("boss", GROUP_ADMIN_ROLE_ID)):
        people[name] = str(uuid.uuid4())
        with signed_in(people[name]):
            client.get("/api/auth/me")
        client.post(f"/api/groups/{group}/members", json={"user_id": people[name], "role_id": str(role)})
    analyse = client.post("/api/analyses", json={"name": "Rôles", "description": "T", "group_ids": [group]}).json()[
        "id"
    ]
    with signed_in("super", group, is_admin=True):
        dossier = client.post("/api/dossiers", json={"name": "D", "analyse_id": analyse}).json()["id"]
    return {"group": group, "analyse": analyse, "dossier": dossier, **people}


def _denied(response) -> str | None:
    detail = response.json().get("detail") if response.status_code == 403 else None
    return detail.get("permission") if isinstance(detail, dict) else None


def test_a_reader_reads_and_changes_nothing(client: TestClient, world: dict) -> None:
    dossier = f"/api/dossiers/{world['dossier']}"
    with signed_in(world["reader"], world["group"]):
        assert client.get(dossier).status_code == 200
        assert client.get(f"{dossier}/permissions").json() == {"permissions": ["dossier.view"]}
        assert _denied(client.put(f"{dossier}/due-at", json={"due_at": None})) == "dossier.edit"
        assert _denied(client.post(f"{dossier}/launch", json={})) == "dossier.run"
        assert _denied(client.delete(dossier)) == "dossier.delete"
        assert _denied(client.post(f"{dossier}/document-drafts", json={})) == "dossier.generate"
        created = client.post("/api/dossiers", json={"name": "Non", "analyse_id": world["analyse"]})
        assert _denied(created) == "dossier.edit"
        assert client.post(f"{dossier}/conversations").status_code == 201  # discuter, c'est consulter


def test_an_instructor_works_on_dossiers_but_neither_deletes_nor_configures(client: TestClient, world: dict) -> None:
    dossier = f"/api/dossiers/{world['dossier']}"
    prompt = f"/api/analyses/{world['analyse']}/classification/prompt"
    with signed_in(world["instructor"], world["group"]):
        assert client.put(f"{dossier}/due-at", json={"due_at": None}).status_code == 200
        assert _denied(client.delete(dossier)) == "dossier.delete"
        assert _denied(client.put(prompt, json={"prompt": "x"})) == "analyse.configure"
    with signed_in(world["boss"], world["group"]):
        assert client.put(prompt, json={"prompt": "x"}).status_code == 200
        assert client.delete(dossier).status_code == 204


def test_the_role_given_on_an_analyse_adds_up(client: TestClient, world: dict) -> None:
    url = f"/api/analyses/{world['analyse']}"
    added = {"user_id": world["reader"], "role_id": str(GROUP_ADMIN_ROLE_ID)}
    client.put(f"{url}/access", json={"group_ids": [world["group"]], "people": [added]})
    with signed_in(world["reader"], world["group"]):
        assert "analyse.configure" in client.get(f"{url}/permissions").json()["permissions"]
        assert client.put(f"{url}/classification/prompt", json={"prompt": "y"}).status_code == 200


def test_bulk_assignment_needs_the_permission_on_every_dossier(client: TestClient, world: dict) -> None:
    body = {"dossier_ids": [world["dossier"]], "assignee_id": world["instructor"]}
    with signed_in(world["reader"], world["group"]):
        assert _denied(client.put("/api/dossiers/bulk-assignee", json=body)) == "dossier.edit"
    with signed_in(world["instructor"], world["group"]):
        assert client.put("/api/dossiers/bulk-assignee", json=body).status_code == 200


def test_every_write_route_asks_for_something() -> None:
    """Une écriture sans permission requise est un choix explicite : la liste est ici."""
    free = set()
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            if method == "get":
                continue
            if path.startswith("/api/dossiers/{dossier_id}"):
                suffix = path.removeprefix("/api/dossiers/{dossier_id}")
                if required_permission.for_dossier(method.upper(), suffix) is None:
                    free.add(suffix.split("/")[1])
            elif path.startswith("/api/analyses/{analyse_id}"):
                if required_permission.for_analyse(path.removeprefix("/api/analyses/{analyse_id}")) is None:
                    free.add("access")
    assert free == {"conversations", "slot", "analyses-dossier", "access"}
    assert required_permission.for_dossier("POST", "/une-route-nouvelle") is Permission.DOSSIER_EDIT


def test_the_shares_list_needs_the_permission(client: TestClient, world: dict) -> None:
    with signed_in(world["instructor"], world["group"]):
        assert _denied(client.get(f"/api/analyses/{world['analyse']}/shares")) == "analyse.access"
    with signed_in(world["boss"], world["group"]):
        assert client.get(f"/api/analyses/{world['analyse']}/shares").status_code == 200


def test_the_list_says_what_can_be_done_on_each_dossier(client: TestClient, world: dict) -> None:
    """Le calcul par page doit dire la même chose que le calcul d'un dossier."""
    for person in (world["reader"], world["instructor"], world["boss"]):
        with signed_in(person, world["group"]):
            listed = client.get("/api/dossiers", params={"page_size": 100}).json()["items"]
            item = next(d for d in listed if d["id"] == world["dossier"])
            single = client.get(f"/api/dossiers/{world['dossier']}/permissions").json()["permissions"]
            assert item["permissions"] == single
