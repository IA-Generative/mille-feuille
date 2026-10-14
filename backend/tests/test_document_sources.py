"""Sources des fichiers : catalogue d'une analyse, sources tampon d'un dossier « à ranger », dépôt avec source."""

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.access_support import As


@pytest.fixture(autouse=True)
def _no_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.routers.dossiers.s3_connector.upload", lambda *args, **kwargs: None)


def _analyse(client: TestClient) -> str:
    return client.post(
        "/api/analyses", json={"name": f"Analyse sources {uuid.uuid4().hex[:6]}", "description": "Analyse de test"}
    ).json()["id"]


def _dossier(client: TestClient, analyse_id: str | None) -> dict:
    body: dict = {"name": f"Dossier sources {uuid.uuid4().hex[:6]}", "visibility": "analyse"}
    if analyse_id:
        body["analyse_id"] = analyse_id
    return client.post("/api/dossiers", json=body).json()


def _source(client: TestClient, analyse_id: str, name: str = "Guichet", description: str = "En main propre") -> dict:
    response = client.post(f"/api/analyses/{analyse_id}/sources", json={"name": name, "description": description})
    assert response.status_code == 201
    return response.json()


def _upload(client: TestClient, dossier_id: str, *, source_id: str | None = None, count: int = 1):
    return client.post(
        f"/api/dossiers/{dossier_id}/documents",
        files=[("files", (f"piece-{i}.pdf", b"fake-bytes", "application/pdf")) for i in range(count)],
        data={"source_id": source_id} if source_id else None,
    )


def test_analyse_catalogue_create_list_update_delete(client: TestClient) -> None:
    analyse_id = _analyse(client)
    source = _source(client, analyse_id, "Courrier", "Pièces reçues par courrier")
    assert source["analyse_id"] == analyse_id
    assert source["dossier_id"] is None

    assert [s["name"] for s in client.get(f"/api/analyses/{analyse_id}/sources").json()] == ["Courrier"]

    updated = client.put(f"/api/sources/{source['id']}", json={"name": "Courrier postal", "description": "Scanné"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Courrier postal"

    assert client.delete(f"/api/sources/{source['id']}").status_code == 204
    assert client.get(f"/api/analyses/{analyse_id}/sources").json() == []


def test_source_name_must_be_unique_in_a_catalogue_and_not_blank(client: TestClient) -> None:
    analyse_id = _analyse(client)
    _source(client, analyse_id, "Guichet")

    assert client.post(f"/api/analyses/{analyse_id}/sources", json={"name": "Guichet"}).status_code == 409
    assert client.post(f"/api/analyses/{analyse_id}/sources", json={"name": "   "}).status_code == 422
    # Un autre catalogue peut réutiliser le nom.
    _source(client, _analyse(client), "Guichet")


def test_upload_with_a_source_applies_to_every_file_of_the_deposit(client: TestClient) -> None:
    analyse_id = _analyse(client)
    source = _source(client, analyse_id)
    dossier = _dossier(client, analyse_id)

    documents = _upload(client, dossier["id"], source_id=source["id"], count=2).json()["documents"]

    assert [d["source"]["id"] for d in documents] == [source["id"], source["id"]]
    assert documents[0]["source"]["description"] == "En main propre"
    assert documents[0]["created_at"]


def test_upload_without_source_and_with_a_foreign_source(client: TestClient) -> None:
    analyse_id = _analyse(client)
    dossier = _dossier(client, analyse_id)
    foreign = _source(client, _analyse(client), "Autre")

    assert _upload(client, dossier["id"]).json()["documents"][0]["source"] is None
    refused = _upload(client, dossier["id"], source_id=foreign["id"])
    assert refused.status_code == 422


def test_adding_files_is_never_refused_whatever_the_dossier_state(client: TestClient) -> None:
    analyse_id = _analyse(client)
    dossier = _dossier(client, analyse_id)
    client.post(f"/api/dossiers/{dossier['id']}/launch")  # en_cours

    running = _upload(client, dossier["id"])
    assert running.status_code == 200
    assert running.json()["status"] == "en_cours"

    client.post(f"/api/dossiers/{dossier['id']}/stop")  # arrêté
    assert _upload(client, dossier["id"]).status_code == 200


def test_dossier_sources_follow_its_analyse(client: TestClient) -> None:
    analyse_id = _analyse(client)
    dossier = _dossier(client, analyse_id)

    created = client.post(f"/api/dossiers/{dossier['id']}/sources", json={"name": "Portail", "description": "En ligne"})
    assert created.status_code == 201
    # Avec une analyse, la source entre dans le catalogue de l'analyse.
    assert created.json()["analyse_id"] == analyse_id
    assert [s["name"] for s in client.get(f"/api/dossiers/{dossier['id']}/sources").json()] == ["Portail"]
    assert [s["name"] for s in client.get(f"/api/analyses/{analyse_id}/sources").json()] == ["Portail"]


def test_a_dossier_a_ranger_keeps_tampon_sources_until_it_gets_an_analyse(client: TestClient) -> None:
    dossier = _dossier(client, None)
    tampon = client.post(f"/api/dossiers/{dossier['id']}/sources", json={"name": "Courrier", "description": "Papier"})
    assert tampon.status_code == 201
    assert tampon.json()["analyse_id"] is None
    assert tampon.json()["dossier_id"] == dossier["id"]
    _upload(client, dossier["id"], source_id=tampon.json()["id"])

    # Sans analyse : visible dans ce dossier seulement.
    assert [s["name"] for s in client.get(f"/api/dossiers/{dossier['id']}/sources").json()] == ["Courrier"]
    assert [s["name"] for s in client.get(f"/api/dossiers/{_dossier(client, None)['id']}/sources").json()] == []

    analyse_id = _analyse(client)
    assigned = client.post(f"/api/dossiers/{dossier['id']}/assign", json={"analyse_id": analyse_id}).json()

    # La source rejoint le catalogue de l'analyse ; le document la garde.
    catalogue = client.get(f"/api/analyses/{analyse_id}/sources").json()
    assert [s["name"] for s in catalogue] == ["Courrier"]
    assert catalogue[0]["dossier_id"] is None
    assert assigned["documents"][0]["source"]["id"] == catalogue[0]["id"]


def test_promotion_merges_a_tampon_with_a_same_named_source_of_the_analyse(client: TestClient) -> None:
    analyse_id = _analyse(client)
    existing = _source(client, analyse_id, "Courrier", "Description de l'analyse")
    dossier = _dossier(client, None)
    tampon = client.post(f"/api/dossiers/{dossier['id']}/sources", json={"name": "Courrier", "description": "Tampon"})
    _upload(client, dossier["id"], source_id=tampon.json()["id"])

    assigned = client.post(f"/api/dossiers/{dossier['id']}/assign", json={"analyse_id": analyse_id}).json()

    assert [s["id"] for s in client.get(f"/api/analyses/{analyse_id}/sources").json()] == [existing["id"]]
    assert assigned["documents"][0]["source"]["id"] == existing["id"]
    assert assigned["documents"][0]["source"]["description"] == "Description de l'analyse"


def test_deleting_a_used_source_leaves_the_documents_without_source(client: TestClient) -> None:
    analyse_id = _analyse(client)
    source = _source(client, analyse_id)
    dossier = _dossier(client, analyse_id)
    _upload(client, dossier["id"], source_id=source["id"])

    assert client.delete(f"/api/sources/{source['id']}").status_code == 204

    documents = client.get(f"/api/dossiers/{dossier['id']}").json()["documents"]
    assert len(documents) == 1
    assert documents[0]["source"] is None


def test_change_and_remove_the_source_of_an_existing_document(client: TestClient) -> None:
    analyse_id = _analyse(client)
    first, second = _source(client, analyse_id, "A"), _source(client, analyse_id, "B")
    dossier = _dossier(client, analyse_id)
    document_id = _upload(client, dossier["id"], source_id=first["id"]).json()["documents"][0]["id"]
    url = f"/api/dossiers/{dossier['id']}/documents/{document_id}/source"

    assert client.put(url, json={"source_id": second["id"]}).json()["source"]["id"] == second["id"]
    assert client.put(url, json={"source_id": None}).json()["source"] is None
    foreign = _source(client, _analyse(client), "Autre")
    assert client.put(url, json={"source_id": foreign["id"]}).status_code == 422


def test_document_added_event_records_the_source_id_but_not_the_file_name(client: TestClient) -> None:
    analyse_id = _analyse(client)
    source = _source(client, analyse_id)
    dossier = _dossier(client, analyse_id)
    _upload(client, dossier["id"], source_id=source["id"])

    events = client.get(f"/api/dossiers/{dossier['id']}/events").json()
    added = next(e for e in (events["items"] if isinstance(events, dict) else events) if e["type"] == "document_added")
    assert added["payload"]["source_id"] == source["id"]
    assert "piece-0.pdf" not in str(added)


def test_a_tampon_source_follows_the_visibility_of_its_dossier(client: TestClient, world: dict) -> None:
    with As(world["alice"]):
        dossier = client.post(
            "/api/dossiers", json={"name": "Dossier restreint", "visibility": "restricted", "group_paths": [world["a"]]}
        ).json()
        tampon = client.post(f"/api/dossiers/{dossier['id']}/sources", json={"name": "Privée"}).json()

    with As(world["bob"]):
        assert client.put(f"/api/sources/{tampon['id']}", json={"name": "Volée"}).status_code == 404
        assert client.delete(f"/api/sources/{tampon['id']}").status_code == 404

    with As(world["alice"]):
        assert client.put(f"/api/sources/{tampon['id']}", json={"name": "Renommée"}).status_code == 200


def test_workers_receive_the_source_of_each_document(client: TestClient) -> None:
    analyse_id = _analyse(client)
    source = _source(client, analyse_id, "Guichet", "En main propre")
    dossier = _dossier(client, analyse_id)
    _upload(client, dossier["id"], source_id=source["id"])
    _upload(client, dossier["id"])

    internal = client.get(
        f"/api/internal/dossiers/{dossier['id']}", headers={"X-App-Token": "dev-only-worker-token-not-for-prod"}
    )

    assert internal.status_code == 200
    sources = [d["source"] for d in internal.json()["documents"]]
    assert {"name": "Guichet", "description": "En main propre"} in sources
    assert None in sources
