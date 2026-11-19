"""Labels et entités d'une analyse : identifiants stables, ordre, et « où chercher » une entité (label et zones)."""

import uuid

from fastapi.testclient import TestClient


def _analyse(client: TestClient) -> str:
    return client.post("/api/analyses", json={"name": f"Portée {uuid.uuid4().hex[:6]}", "description": "T"}).json()[
        "id"
    ]


def _put_labels(client: TestClient, analyse_id: str, labels: list[dict]):
    return client.put(f"/api/analyses/{analyse_id}/classification/labels", json={"labels": labels})


def _put_entities(client: TestClient, analyse_id: str, entities: list[dict]):
    return client.put(f"/api/analyses/{analyse_id}/extraction/entities", json={"entities": entities})


def _entity(name: str, **extra) -> dict:
    return {"name": name, "definition": "", "type": "texte", **extra}


def _labels(client: TestClient, analyse_id: str) -> list[dict]:
    return client.get(f"/api/analyses/{analyse_id}").json()["classification"]["labels"]


def _entities(client: TestClient, analyse_id: str) -> list[dict]:
    return client.get(f"/api/analyses/{analyse_id}").json()["extraction"]["entities"]


def test_labels_keep_their_identity_and_order(client: TestClient) -> None:
    analyse_id = _analyse(client)
    first = _put_labels(client, analyse_id, [{"name": "CNI"}, {"name": "RIB"}]).json()["classification"]["labels"]
    cni, rib = first

    # Même identité malgré le renommage et l'inversion de l'ordre.
    again = _put_labels(
        client, analyse_id, [{"id": rib["id"], "name": "RIB (IBAN)"}, {"id": cni["id"], "name": "CNI"}]
    ).json()["classification"]["labels"]

    assert [(label["id"], label["name"]) for label in again] == [(rib["id"], "RIB (IBAN)"), (cni["id"], "CNI")]


def test_a_label_of_another_analyse_is_refused(client: TestClient) -> None:
    other = _put_labels(client, _analyse(client), [{"name": "Autre"}]).json()["classification"]["labels"][0]

    response = _put_labels(client, _analyse(client), [{"id": other["id"], "name": "Autre"}])

    assert response.status_code == 422


def test_an_entity_searches_in_a_label_and_zones(client: TestClient) -> None:
    analyse_id = _analyse(client)
    label = _put_labels(client, analyse_id, [{"name": "CNI"}]).json()["classification"]["labels"][0]
    zone = {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.4}

    saved = _put_entities(
        client, analyse_id, [_entity("nom", label_id=label["id"], zones=[zone]), _entity("ville")]
    ).json()["extraction"]["entities"]

    assert saved[0]["label_id"] == label["id"] and saved[0]["zones"] == [{**zone, "example_id": None}]
    assert saved[1]["label_id"] is None and saved[1]["zones"] == []  # sans portée : tout le dossier


def test_an_entity_keeps_its_identity_when_saved_again(client: TestClient) -> None:
    analyse_id = _analyse(client)
    first = _put_entities(client, analyse_id, [_entity("nom")]).json()["extraction"]["entities"][0]

    again = _put_entities(client, analyse_id, [{**first, "definition": "Nom de famille"}]).json()["extraction"]
    assert [(e["id"], e["definition"]) for e in again["entities"]] == [(first["id"], "Nom de famille")]


def test_an_entity_cannot_point_to_an_unknown_label(client: TestClient) -> None:
    analyse_id = _analyse(client)

    response = _put_entities(client, analyse_id, [_entity("nom", label_id=str(uuid.uuid4()))])

    assert response.status_code == 422


def test_invalid_zones_are_refused(client: TestClient) -> None:
    analyse_id = _analyse(client)
    for zone in (
        {"x0": 0.5, "y0": 0.1, "x1": 0.2, "y1": 0.4},  # largeur négative
        {"x0": 0.1, "y0": 0.1, "x1": 1.4, "y1": 0.4},  # hors de la page
    ):
        assert _put_entities(client, analyse_id, [_entity("nom", zones=[zone])]).status_code == 422


def test_a_label_used_by_an_entity_cannot_be_removed(client: TestClient) -> None:
    analyse_id = _analyse(client)
    label = _put_labels(client, analyse_id, [{"name": "CNI"}]).json()["classification"]["labels"][0]
    _put_entities(client, analyse_id, [_entity("nom", label_id=label["id"])])

    response = _put_labels(client, analyse_id, [])

    assert response.status_code == 422 and "nom" in response.json()["detail"]
    assert len(_labels(client, analyse_id)) == 1

    # Une fois l'entité détachée, le label peut partir.
    _put_entities(client, analyse_id, [_entity("nom")])
    assert _put_labels(client, analyse_id, []).status_code == 200


def test_restoring_entities_brings_back_label_and_zones(client: TestClient) -> None:
    analyse_id = _analyse(client)
    label = _put_labels(client, analyse_id, [{"name": "CNI"}]).json()["classification"]["labels"][0]
    zone = {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.4}
    _put_entities(client, analyse_id, [_entity("nom", label_id=label["id"], zones=[zone])])
    _put_entities(client, analyse_id, [_entity("nom")])  # l'entité perd sa portée

    versions = client.get(f"/api/analyses/{analyse_id}").json()["extraction"]["entities_versions"]
    before_scope_lost = versions[0]["id"]  # la plus récente : l'état juste avant la dernière modification
    restored = client.post(f"/api/analyses/{analyse_id}/extraction/entities/restore/{before_scope_lost}")

    assert restored.status_code == 200
    entity = _entities(client, analyse_id)[0]
    assert entity["label_id"] == label["id"] and entity["zones"] == [{**zone, "example_id": None}]


def test_restoring_labels_brings_back_the_previous_list(client: TestClient) -> None:
    analyse_id = _analyse(client)
    _put_labels(client, analyse_id, [{"name": "CNI"}])
    _put_labels(client, analyse_id, [{"name": "RIB"}])

    versions = client.get(f"/api/analyses/{analyse_id}").json()["classification"]["labels_versions"]
    restored = client.post(f"/api/analyses/{analyse_id}/classification/labels/restore/{versions[0]['id']}")

    assert restored.status_code == 200
    assert [label["name"] for label in _labels(client, analyse_id)] == ["CNI"]


# --- Labels de chaque page (lus par le worker d'extraction) ---

INTERNAL = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


def _classified_dossier(client: TestClient, monkeypatch) -> dict:
    """Un dossier de deux pages : la page 1 classée CNI, la page 2 RIB, comme le fait le worker."""
    for name in ("dispatch_classification", "dispatch_entity_extraction", "dispatch_agent_execution"):
        monkeypatch.setattr(f"app.routers.dossiers.{name}", lambda dossier_id, *args, **kwargs: None)
    analyse_id = _analyse(client)
    cni, rib = _put_labels(client, analyse_id, [{"name": "CNI"}, {"name": "RIB"}]).json()["classification"]["labels"]
    dossier_id = client.post("/api/dossiers", json={"name": "Dossier", "analyse_id": analyse_id}).json()["id"]
    document = client.post(
        f"/api/dossiers/{dossier_id}/documents", files=[("files", ("a.pdf", b"x", "application/pdf"))]
    ).json()["documents"][0]
    pages = [
        client.post(
            f"/api/internal/documents/{document['id']}/pages",
            json={"page_number": n, "content": f"page {n}"},
            headers=INTERNAL,
        ).json()
        for n in (1, 2)
    ]
    client.post(f"/api/dossiers/{dossier_id}/launch")
    for page, label in zip(pages, (cni, rib), strict=True):
        unit = client.post(
            f"/api/internal/dossiers/{dossier_id}/analysis-units",
            json={"kind": "classification", "description": {}},
            headers=INTERNAL,
        ).json()
        client.post(
            f"/api/internal/pages/{page['id']}/predictions",
            json={
                "kind": "label",
                "name": label["name"],
                "value": label["name"],
                "label_definition_id": label["id"],
                "unit_id": unit["id"],
            },
            headers=INTERNAL,
        )
    return {"id": dossier_id, "pages": pages, "cni": cni, "rib": rib}


def _page_labels(client: TestClient, dossier_id: str) -> dict[str, list[str]]:
    return client.get(f"/api/internal/dossiers/{dossier_id}/page-labels", headers=INTERNAL).json()["pages"]


def test_each_page_reports_the_label_it_is_classified_in(client: TestClient, monkeypatch) -> None:
    dossier = _classified_dossier(client, monkeypatch)
    page_1, page_2 = (page["id"] for page in dossier["pages"])

    assert _page_labels(client, dossier["id"]) == {page_1: [dossier["cni"]["id"]], page_2: [dossier["rib"]["id"]]}


def test_an_instructor_correction_wins_over_the_model(client: TestClient, monkeypatch) -> None:
    dossier = _classified_dossier(client, monkeypatch)
    page_1 = dossier["pages"][0]["id"]
    analysis = client.get(f"/api/dossiers/{dossier['id']}/analyse-dossier").json()
    element = next(e for e in analysis["elements"] if e["first_page_number"] == 1)

    response = client.post(
        f"/api/dossiers/{dossier['id']}/analyses-dossier/{analysis['id']}/elements/{element['id']}/versions",
        json={"value": {"label": "RIB"}, "reason": "C'est un RIB"},
    )

    assert response.status_code == 201
    assert _page_labels(client, dossier["id"])[page_1] == [dossier["rib"]["id"]]
