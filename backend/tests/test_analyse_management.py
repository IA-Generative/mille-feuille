"""Modifier le nom et la description d'une analyse, les restaurer, la supprimer : le créateur et les administrateurs."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, update

from app.db import async_session_factory
from app.models.analyse import Analyse
from app.models.dossier import Dossier
from tests.access_support import As


def make_analyse(client: TestClient, person=None) -> dict:  # noqa: ANN001
    body = {"name": f"Gestion {uuid.uuid4().hex[:6]}", "description": "Décrit le but."}
    if person is None:
        return client.post("/api/analyses", json=body).json()
    with As(person):
        return client.post("/api/analyses", json=body).json()


def forget_creator(client: TestClient, analyse_id: str) -> None:
    async def clear() -> None:
        async with async_session_factory() as db:
            await db.execute(update(Analyse).where(Analyse.id == uuid.UUID(analyse_id)).values(created_by=None))
            await db.commit()

    client.portal.call(clear)


def test_an_analyse_remembers_who_created_it(client: TestClient, world: dict) -> None:
    analyse = make_analyse(client, world["alice"])

    assert analyse["created_by"] == world["alice"].user_id
    listed = client.get("/api/analyses", params={"q": analyse["name"]}).json()["items"]
    assert [item["created_by"] for item in listed] == [world["alice"].user_id]


def test_the_creator_changes_the_name_and_the_description_and_the_old_ones_go_to_the_history(
    client: TestClient, world: dict
) -> None:
    analyse = make_analyse(client, world["alice"])

    with As(world["alice"]):
        response = client.put(
            f"/api/analyses/{analyse['id']}", json={"name": "  Nouveau nom ", "description": "Nouvelle description."}
        )

    body = response.json()
    assert response.status_code == 200
    assert (body["name"], body["description"]) == ("Nouveau nom", "Nouvelle description.")
    assert [v["content"] for v in body["name_versions"]] == [analyse["name"]]
    assert [v["content"] for v in body["description_versions"]] == ["Décrit le but."]


def test_changing_only_one_of_the_two_records_only_that_one(client: TestClient, world: dict) -> None:
    analyse = make_analyse(client, world["alice"])

    with As(world["alice"]):
        body = client.put(
            f"/api/analyses/{analyse['id']}", json={"name": analyse["name"], "description": "Autre."}
        ).json()

    assert body["name_versions"] == [] and len(body["description_versions"]) == 1


def test_saving_the_same_values_adds_no_version(client: TestClient, world: dict) -> None:
    analyse = make_analyse(client, world["alice"])

    with As(world["alice"]):
        body = client.put(
            f"/api/analyses/{analyse['id']}", json={"name": analyse["name"], "description": analyse["description"]}
        ).json()

    assert body["name_versions"] == [] and body["description_versions"] == [] and body["version"] == analyse["version"]


def test_renaming_does_not_change_the_version_of_the_analyse_but_the_description_does(
    client: TestClient, world: dict
) -> None:
    analyse = make_analyse(client, world["alice"])

    with As(world["alice"]):
        renamed = client.put(
            f"/api/analyses/{analyse['id']}", json={"name": "Autre nom", "description": analyse["description"]}
        ).json()
        described = client.put(
            f"/api/analyses/{analyse['id']}", json={"name": "Autre nom", "description": "Autre description."}
        ).json()

    assert renamed["version"] == analyse["version"]
    assert described["version"] != analyse["version"]


def test_the_name_and_the_description_stay_required(client: TestClient, world: dict) -> None:
    analyse = make_analyse(client, world["alice"])

    with As(world["alice"]):
        url = f"/api/analyses/{analyse['id']}"
        assert client.put(url, json={"name": "   ", "description": "x"}).status_code == 422
        assert client.put(url, json={"name": "x", "description": "   "}).status_code == 422
        assert client.put(url, json={"name": "x"}).status_code == 422


def test_an_old_name_and_an_old_description_can_be_restored(client: TestClient, world: dict) -> None:
    analyse = make_analyse(client, world["alice"])
    url = f"/api/analyses/{analyse['id']}"
    with As(world["alice"]):
        changed = client.put(url, json={"name": "Autre nom", "description": "Autre description."}).json()

        name_back = client.post(f"{url}/name/restore/{changed['name_versions'][0]['id']}").json()
        both_back = client.post(f"{url}/description/restore/{changed['description_versions'][0]['id']}").json()

    assert name_back["name"] == analyse["name"] and name_back["description"] == "Autre description."
    assert both_back["description"] == "Décrit le but."
    # La valeur remplacée par la restauration devient elle-même une version.
    assert [v["content"] for v in name_back["name_versions"]][0] == "Autre nom"


def test_restoring_an_unknown_version_is_a_404(client: TestClient, world: dict) -> None:
    analyse = make_analyse(client, world["alice"])

    with As(world["alice"]):
        response = client.post(f"/api/analyses/{analyse['id']}/name/restore/{uuid.uuid4()}")

    assert response.status_code == 404


def test_someone_else_can_neither_change_restore_nor_delete(client: TestClient, world: dict) -> None:
    analyse = make_analyse(client, world["alice"])
    url = f"/api/analyses/{analyse['id']}"
    with As(world["alice"]):
        changed = client.put(url, json={"name": "Autre nom", "description": "Autre."}).json()

    with As(world["bob"]):
        assert client.put(url, json={"name": "Piraté", "description": "x"}).status_code == 403
        assert client.post(f"{url}/name/restore/{changed['name_versions'][0]['id']}").status_code == 403
        assert client.delete(url).status_code == 403
        # Elle reste lisible et modifiable dans ses autres parties, comme avant.
        assert client.get(url).json()["name"] == "Autre nom"


def test_an_administrator_manages_any_analyse(client: TestClient, world: dict) -> None:
    analyse = make_analyse(client, world["alice"])
    url = f"/api/analyses/{analyse['id']}"

    with As(world["root"]):
        assert client.put(url, json={"name": "Par l'admin", "description": "x"}).status_code == 200
        assert client.delete(url).status_code == 204

    assert client.get(url).status_code == 404


def test_an_analyse_without_a_known_creator_is_for_administrators_only(client: TestClient, world: dict) -> None:
    analyse = make_analyse(client, world["alice"])
    forget_creator(client, analyse["id"])
    url = f"/api/analyses/{analyse['id']}"

    with As(world["alice"]):
        assert client.put(url, json={"name": "x", "description": "x"}).status_code == 403
        assert client.delete(url).status_code == 403
    with As(world["root"]):
        assert client.put(url, json={"name": "x", "description": "x"}).status_code == 200


def test_the_creator_deletes_the_analyse_with_its_content(client: TestClient, world: dict) -> None:
    analyse = make_analyse(client, world["alice"])
    url = f"/api/analyses/{analyse['id']}"

    with As(world["alice"]):
        client.put(url, json={"name": "Autre nom", "description": "Autre."})
        response = client.delete(url)

    assert response.status_code == 204 and client.get(url).status_code == 404
    assert client.delete(url).status_code == 404


def test_an_analyse_that_still_has_dossiers_is_not_deleted(client: TestClient, world: dict) -> None:
    analyse = make_analyse(client, world["alice"])
    url = f"/api/analyses/{analyse['id']}"
    with As(world["alice"]):
        dossier = client.post("/api/dossiers", json={"name": "Dossier", "analyse_id": analyse["id"]}).json()

        response = client.delete(url)

        assert response.status_code == 409 and "1 dossier" in response.json()["detail"]
        assert client.get(url).status_code == 200

    # Aucune route ne supprime un dossier : une fois retiré de la base, l'analyse peut l'être.
    async def remove_dossier() -> None:
        async with async_session_factory() as db:
            await db.execute(delete(Dossier).where(Dossier.id == uuid.UUID(dossier["id"])))
            await db.commit()

    client.portal.call(remove_dossier)
    with As(world["alice"]):
        assert client.delete(url).status_code == 204


def test_the_other_restore_routes_still_work(client: TestClient, world: dict) -> None:
    """Les routes `/{id}/<champ>/restore/{version}` existantes ne sont pas masquées par celles du nom et de la
    description."""
    analyse = make_analyse(client, world["alice"])

    with As(world["alice"]):
        response = client.post(f"/api/analyses/{analyse['id']}/statuses/restore/{uuid.uuid4()}")

    assert response.status_code != 403 and response.status_code in (404, 422)
