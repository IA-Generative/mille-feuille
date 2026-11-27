"""Thèmes d'analyses : gestion par les administrateurs, rangement d'une analyse, pagination par thème, historiques."""

import uuid

from fastapi.testclient import TestClient

from tests.access_support import As


def make_theme(client: TestClient, description: str = "") -> dict:
    response = client.post(
        "/api/analyse-themes", json={"name": f"Thème {uuid.uuid4().hex[:8]}", "description": description}
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_analyse(client: TestClient, name: str = "Rangée") -> dict:
    return client.post("/api/analyses", json={"name": name, "description": "But."}).json()


def move(client: TestClient, analyse_id: str, theme_id: str | None) -> dict:
    response = client.put(f"/api/analyses/{analyse_id}/theme", json={"theme_id": theme_id})
    assert response.status_code == 200, response.text
    return response.json()


def test_only_administrators_manage_themes(client: TestClient, world: dict) -> None:
    theme = make_theme(client)

    with As(world["alice"]):
        assert client.post("/api/analyse-themes", json={"name": "Interdit"}).status_code == 403
        assert client.put(f"/api/analyse-themes/{theme['id']}", json={"name": "Interdit"}).status_code == 403
        assert client.delete(f"/api/analyse-themes/{theme['id']}").status_code == 403
        assert client.get("/api/analyse-themes").status_code == 200


def test_a_name_is_unique_whatever_the_case_and_cannot_be_blank(client: TestClient) -> None:
    theme = make_theme(client)

    assert client.post("/api/analyse-themes", json={"name": theme["name"].upper()}).status_code == 409
    assert client.post("/api/analyse-themes", json={"name": "   "}).status_code == 422


def test_the_old_name_and_description_are_kept_and_can_be_restored(client: TestClient) -> None:
    theme = make_theme(client, "Avant")

    changed = client.put(
        f"/api/analyse-themes/{theme['id']}", json={"name": f"{theme['name']} bis", "description": "Après"}
    ).json()
    assert [v["content"] for v in changed["name_versions"]] == [theme["name"]]
    assert [v["content"] for v in changed["description_versions"]] == ["Avant"]

    version_id = changed["description_versions"][0]["id"]
    restored = client.post(f"/api/analyse-themes/{theme['id']}/versions/{version_id}/restore").json()
    assert restored["description"] == "Avant"
    assert restored["name"] == changed["name"]
    assert "Après" in [v["content"] for v in restored["description_versions"]]


def test_analyses_are_counted_and_paginated_by_theme(client: TestClient) -> None:
    theme = make_theme(client)
    marker = uuid.uuid4().hex[:8]
    themed = [make_analyse(client, f"{marker} {i}") for i in range(3)]
    loose = make_analyse(client, f"{marker} libre")
    for analyse in themed:
        move(client, analyse["id"], theme["id"])

    listed = client.get("/api/analyse-themes", params={"q": marker}).json()
    assert next(t for t in listed["items"] if t["id"] == theme["id"])["analyse_count"] == 3
    assert listed["unthemed_count"] == 1

    page = client.get("/api/analyses", params={"theme_id": theme["id"], "page_size": 2, "page": 2}).json()
    assert (page["total"], page["pages"], len(page["items"])) == (3, 2, 1)
    assert page["items"][0]["theme_id"] == theme["id"]

    unthemed = client.get("/api/analyses", params={"unthemed": True, "q": marker}).json()
    assert [a["id"] for a in unthemed["items"]] == [loose["id"]]


def test_moving_an_analyse_is_historised_without_changing_its_version(client: TestClient) -> None:
    first, second = make_theme(client), make_theme(client)
    analyse = make_analyse(client)

    move(client, analyse["id"], first["id"])
    moved = move(client, analyse["id"], second["id"])

    assert moved["version"] == analyse["version"]
    assert moved["theme_versions"][0]["content"] == {"theme_id": first["id"], "name": first["name"]}
    assert len(move(client, analyse["id"], second["id"])["theme_versions"]) == 2

    version_id = moved["theme_versions"][0]["id"]
    restored = client.post(f"/api/analyses/{analyse['id']}/theme/restore/{version_id}")
    assert restored.json()["theme_id"] == first["id"]


def test_deleting_a_theme_keeps_its_analyses(client: TestClient) -> None:
    theme = make_theme(client)
    analyse = make_analyse(client)
    move(client, analyse["id"], theme["id"])

    assert client.delete(f"/api/analyse-themes/{theme['id']}").status_code == 204

    assert client.get(f"/api/analyses/{analyse['id']}").json()["theme_id"] is None


def test_moving_an_analyse_needs_the_permission(client: TestClient, world: dict, without_role) -> None:
    without_role(world["bob"].user_id)
    theme = make_theme(client)
    with As(world["alice"]):
        analyse = make_analyse(client)

    with As(world["bob"]):
        assert client.put(f"/api/analyses/{analyse['id']}/theme", json={"theme_id": theme["id"]}).status_code == 403
    with As(world["alice"]):
        move(client, analyse["id"], theme["id"])
    assert client.put(f"/api/analyses/{analyse['id']}/theme", json={"theme_id": str(uuid.uuid4())}).status_code == 404
