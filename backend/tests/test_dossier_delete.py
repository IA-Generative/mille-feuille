"""Supprimer un dossier : un administrateur, ou la personne qui l'a créé."""

from fastapi.testclient import TestClient

from tests.access_support import As, _person  # noqa: F401


def _create(client: TestClient, analyse: dict) -> dict:
    response = client.post("/api/dossiers", json={"name": "À supprimer", "analyse_id": analyse["id"]})
    assert response.status_code == 201, response.text
    return response.json()


def test_the_person_who_created_the_dossier_can_delete_it(client: TestClient, world: dict, analyse: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
        assert client.get(f"/api/dossiers/{dossier['id']}").json()["can_delete"] is True

        assert client.delete(f"/api/dossiers/{dossier['id']}").status_code == 204
        assert client.get(f"/api/dossiers/{dossier['id']}").status_code == 404


def test_an_administrator_can_delete_any_dossier(client: TestClient, world: dict, analyse: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
    with As(world["root"]):
        assert client.get(f"/api/dossiers/{dossier['id']}").json()["can_delete"] is True
        assert client.delete(f"/api/dossiers/{dossier['id']}").status_code == 204


def test_someone_else_who_can_see_the_dossier_cannot_delete_it(client: TestClient, world: dict, analyse: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
    with As(world["bob"]):
        assert client.get(f"/api/dossiers/{dossier['id']}").json()["can_delete"] is False
        assert client.delete(f"/api/dossiers/{dossier['id']}").status_code == 403
    with As(world["alice"]):
        assert client.get(f"/api/dossiers/{dossier['id']}").status_code == 200
