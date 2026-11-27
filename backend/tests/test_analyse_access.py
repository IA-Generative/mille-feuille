"""Qui voit une analyse, et ce qui en découle (#662), avec la vraie règle."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.core.security.factory import RequestContext, get_current_user
from app.main import app


@pytest.fixture(autouse=True)
def open_analyses() -> None:
    """Remplace le préalable de conftest.py : ici, la vraie règle."""


@contextmanager
def signed_in(user_id: str, *groups: str, is_admin: bool = False) -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: RequestContext(
        user_id=user_id, email=f"{user_id}@example.org", roles=[], is_admin=is_admin, groups=list(groups)
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _group(client: TestClient) -> str:
    return client.post("/api/groups", json={"name": f"G {uuid.uuid4().hex[:8]}"}).json()["id"]


def _analyse(client: TestClient, *groups: str) -> str:
    response = client.post(
        "/api/analyses", json={"name": f"A {uuid.uuid4().hex[:8]}", "description": "T", "group_ids": list(groups)}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _listed(client: TestClient) -> set[str]:
    ids, page = set(), 1
    while True:
        body = client.get("/api/analyses", params={"page": page, "page_size": 100}).json()
        ids |= {a["id"] for a in body["items"]}
        if page >= body["pages"]:
            return ids
        page += 1


@pytest.fixture
def world(client: TestClient) -> dict:
    group, other = _group(client), _group(client)
    return {"group": group, "other": other, "analyse": _analyse(client, group), "orphan": _analyse(client)}


def test_an_analyse_is_seen_by_its_groups_and_super_admins_only(client: TestClient, world: dict) -> None:
    with signed_in("membre", world["group"]):
        assert world["analyse"] in _listed(client)
        assert world["orphan"] not in _listed(client)
        assert client.get(f"/api/analyses/{world['analyse']}").status_code == 200
        assert client.get(f"/api/analyses/{world['orphan']}").status_code == 404
    with signed_in("etranger", world["other"]):
        assert world["analyse"] not in _listed(client)
        assert client.get(f"/api/analyses/{world['analyse']}").status_code == 404
        themes = client.get("/api/analyse-themes").json()
        assert themes["unthemed_count"] == 0
    with signed_in("super", is_admin=True):
        assert {world["analyse"], world["orphan"]} <= _listed(client)


def test_no_route_under_an_analyse_answers_a_stranger(client: TestClient, world: dict) -> None:
    """Toute opération sous `/api/analyses/{analyse_id}` répond 404 : une route ajoutée plus tard est testée aussi."""
    checked = 0
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith("/api/analyses/{analyse_id}"):
            continue
        url = path.replace("{analyse_id}", world["analyse"])
        while "{" in url:
            start = url.index("{")
            url = url[:start] + str(uuid.uuid4()) + url[url.index("}", start) + 1 :]
        for method in operations:
            with signed_in("etranger", world["other"]):
                response = client.request(method.upper(), url, json={})
            assert response.status_code == 404, f"{method.upper()} {path} → {response.status_code}"
            checked += 1
    assert checked > 40


def test_only_group_admins_and_super_admins_create_analyses(client: TestClient, world: dict) -> None:
    person = str(uuid.uuid4())
    with signed_in(person):
        client.get("/api/auth/me")
    client.post(
        f"/api/groups/{world['group']}/members",
        json={"user_id": person, "role_id": "00000000-0000-4000-8000-000000000001"},
    )
    body = {"name": "Nouvelle", "description": "T"}

    with signed_in("simple", world["group"]):
        assert client.post("/api/analyses", json=body).status_code == 403
    with signed_in(person, world["group"]):
        foreign = client.post("/api/analyses", json={**body, "group_ids": [world["other"]]})
        assert foreign.json()["detail"]["code"] == "group_not_yours"
        none = client.post("/api/analyses", json={**body, "group_ids": []})
        assert none.json()["detail"]["code"] == "groups_required"
        created = client.post("/api/analyses", json=body)
        assert created.status_code == 201
        assert created.json()["id"] in _listed(client)


def test_dossiers_following_their_analyse_follow_its_access(client: TestClient, world: dict) -> None:
    with signed_in("super", is_admin=True):
        dossier = client.post(
            "/api/dossiers", json={"name": "Selon l'analyse", "analyse_id": world["analyse"], "visibility": "analyse"}
        ).json()["id"]

    with signed_in("membre", world["group"]):
        assert client.get(f"/api/dossiers/{dossier}").status_code == 200
    with signed_in("etranger", world["other"]):
        assert client.get(f"/api/dossiers/{dossier}").status_code == 404
        listed = client.get("/api/dossiers", params={"page_size": 100}).json()["items"]
        assert dossier not in {d["id"] for d in listed}
        tracked = client.get("/api/tracking", params={"analyse_id": world["analyse"]}).json()
        assert dossier not in str(tracked)
        refused = client.post("/api/dossiers", json={"name": "Intrus", "analyse_id": world["analyse"]})
        assert refused.json()["detail"] == "Analyse introuvable"


def test_the_directory_proposes_only_people_who_see_the_analyse(client: TestClient, world: dict) -> None:
    inside, outside = str(uuid.uuid4()), str(uuid.uuid4())
    for user_id, group in ((inside, world["group"]), (outside, world["other"])):
        with signed_in(user_id, group):
            client.get("/api/auth/me")
    with signed_in("super", is_admin=True):
        dossier = client.post(
            "/api/dossiers", json={"name": "D", "analyse_id": world["analyse"], "visibility": "analyse"}
        ).json()["id"]
        assert client.put(f"/api/dossiers/{dossier}/assignee", json={"assignee_id": outside}).status_code == 422
        assert client.put(f"/api/dossiers/{dossier}/assignee", json={"assignee_id": inside}).status_code == 200


def _person(client: TestClient) -> str:
    user_id = str(uuid.uuid4())
    with signed_in(user_id):
        client.get("/api/auth/me")
    return user_id


def _group_admin(client: TestClient, group_id: str) -> str:
    person = _person(client)
    client.post(
        f"/api/groups/{group_id}/members",
        json={"user_id": person, "role_id": "00000000-0000-4000-8000-000000000001"},
    )
    return person


ADMIN_ROLE, READER = "00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000003"


def test_an_added_person_sees_the_analyse_until_removed_and_history_restores(client: TestClient, world: dict) -> None:
    url, person = f"/api/analyses/{world['analyse']}/access", _person(client)
    added = client.put(
        url, json={"group_ids": [world["group"]], "people": [{"user_id": person, "role_id": READER}]}
    ).json()
    assert [(p["pending"], p["role_id"]) for p in added["people"]] == [(False, READER)]
    with signed_in(person):
        assert client.get(f"/api/analyses/{world['analyse']}").status_code == 200
        seen = client.get(url).json()
        assert (seen["can_edit"], seen["people"][0]["email"], seen["versions"]) == (False, "", [])
        assert client.put(url, json={"group_ids": []}).status_code == 403

    removed = client.put(url, json={"group_ids": [world["group"]], "people": []}).json()
    with signed_in(person):
        assert client.get(f"/api/analyses/{world['analyse']}").status_code == 404

    client.post(f"{url}/restore/{removed['versions'][0]['id']}")
    with signed_in(person):
        assert client.get(f"/api/analyses/{world['analyse']}").status_code == 200


def test_a_group_admin_changes_only_their_groups_and_keeps_one(client: TestClient, world: dict) -> None:
    url, boss = f"/api/analyses/{world['analyse']}/access", _group_admin(client, world["group"])
    with signed_in(boss, world["group"]):
        assert client.get(url).json()["can_edit"] is True
        other = client.put(url, json={"group_ids": [world["group"], world["other"]]})
        assert other.json()["detail"]["code"] == "group_not_yours"
        assert client.put(url, json={"group_ids": []}).json()["detail"]["code"] == "groups_required"
        outside = {"email": "Externe@Example.org", "role_id": READER}
        saved = client.put(url, json={"group_ids": [world["group"]], "people": [outside]}).json()
        assert [(p["email"], p["pending"]) for p in saved["people"]] == [("externe@example.org", True)]
        kept = {"id": saved["people"][0]["id"], "role_id": ADMIN_ROLE}
        assert client.put(url, json={"group_ids": [world["group"]], "people": [kept]}).status_code == 200


def test_nobody_grants_a_wider_role_on_an_analyse(client: TestClient, world: dict) -> None:
    role = client.post(
        "/api/roles", json={"name": f"R {uuid.uuid4().hex[:8]}", "permissions": ["analyse.access", "dossier.view"]}
    ).json()["id"]
    person = _person(client)
    client.post(f"/api/groups/{world['group']}/members", json={"user_id": person, "role_id": role})
    url = f"/api/analyses/{world['analyse']}/access"

    with signed_in(person, world["group"]):
        wide = {"group_ids": [world["group"]], "people": [{"email": "a@example.org", "role_id": ADMIN_ROLE}]}
        assert client.put(url, json=wide).json()["detail"]["code"] == "role_too_wide"
        narrow = {"group_ids": [world["group"]], "people": [{"email": "a@example.org", "role_id": READER}]}
        assert client.put(url, json=narrow).status_code == 200


def test_a_group_or_role_used_by_an_analyse_is_not_deleted(client: TestClient, world: dict) -> None:
    assert client.delete(f"/api/groups/{world['group']}").json()["detail"]["code"] == "group_in_use"
