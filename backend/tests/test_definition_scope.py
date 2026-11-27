"""Labels et entités d'une analyse : identifiants stables, ordre, exemples de label, et « où chercher » une entité
(un ou plusieurs labels, et des zones)."""

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


def test_an_entity_searches_in_one_or_several_labels_and_zones(client: TestClient) -> None:
    analyse_id = _analyse(client)
    cni, passeport = _put_labels(client, analyse_id, [{"name": "CNI"}, {"name": "Passeport"}]).json()["classification"][
        "labels"
    ]
    zone = {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.4}

    saved = _put_entities(
        client,
        analyse_id,
        [
            _entity("nom", label_ids=[cni["id"], passeport["id"]], zones=[zone]),
            _entity("numéro", label_ids=[cni["id"]]),
            _entity("ville"),
        ],
    ).json()["extraction"]["entities"]

    assert saved[0]["label_ids"] == [cni["id"], passeport["id"]]
    assert saved[0]["zones"] == [{**zone, "example_id": None}]
    assert saved[1]["label_ids"] == [cni["id"]]
    assert saved[2]["label_ids"] == [] and saved[2]["zones"] == []  # sans portée : tout le dossier


def test_an_entity_keeps_its_identity_when_saved_again(client: TestClient) -> None:
    analyse_id = _analyse(client)
    first = _put_entities(client, analyse_id, [_entity("nom")]).json()["extraction"]["entities"][0]

    again = _put_entities(client, analyse_id, [{**first, "definition": "Nom de famille"}]).json()["extraction"]
    assert [(e["id"], e["definition"]) for e in again["entities"]] == [(first["id"], "Nom de famille")]


def test_an_entity_cannot_point_to_an_unknown_label(client: TestClient) -> None:
    analyse_id = _analyse(client)

    response = _put_entities(client, analyse_id, [_entity("nom", label_ids=[str(uuid.uuid4())])])

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
    _put_entities(client, analyse_id, [_entity("nom", label_ids=[label["id"]])])

    response = _put_labels(client, analyse_id, [])

    assert response.status_code == 422 and "nom" in response.json()["detail"]
    assert len(_labels(client, analyse_id)) == 1

    # Une fois l'entité détachée, le label peut partir.
    _put_entities(client, analyse_id, [_entity("nom")])
    assert _put_labels(client, analyse_id, []).status_code == 200


def test_restoring_entities_brings_back_labels_and_zones(client: TestClient) -> None:
    analyse_id = _analyse(client)
    label = _put_labels(client, analyse_id, [{"name": "CNI"}]).json()["classification"]["labels"][0]
    zone = {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.4}
    _put_entities(client, analyse_id, [_entity("nom", label_ids=[label["id"]], zones=[zone])])
    _put_entities(client, analyse_id, [_entity("nom")])  # l'entité perd sa portée

    versions = client.get(f"/api/analyses/{analyse_id}").json()["extraction"]["entities_versions"]
    before_scope_lost = versions[0]["id"]  # la plus récente : l'état juste avant la dernière modification
    restored = client.post(f"/api/analyses/{analyse_id}/extraction/entities/restore/{before_scope_lost}")

    assert restored.status_code == 200
    entity = _entities(client, analyse_id)[0]
    assert entity["label_ids"] == [label["id"]] and entity["zones"] == [{**zone, "example_id": None}]


def test_restoring_labels_brings_back_the_previous_list(client: TestClient) -> None:
    analyse_id = _analyse(client)
    _put_labels(client, analyse_id, [{"name": "CNI"}])
    _put_labels(client, analyse_id, [{"name": "RIB"}])

    versions = client.get(f"/api/analyses/{analyse_id}").json()["classification"]["labels_versions"]
    restored = client.post(f"/api/analyses/{analyse_id}/classification/labels/restore/{versions[0]['id']}")

    assert restored.status_code == 200
    assert [label["name"] for label in _labels(client, analyse_id)] == ["CNI"]


# --- Documents d'exemple d'un label ---


def _upload(client: TestClient, analyse_id: str, label_id: str, *names: str, content_type: str = "image/png"):
    files = [("files", (name, b"\x89PNG-" + name.encode(), content_type)) for name in names]
    return client.post(f"/api/analyses/{analyse_id}/classification/labels/{label_id}/examples", files=files)


def _label_with_examples(client: TestClient, *names: str) -> tuple[str, dict]:
    analyse_id = _analyse(client)
    label = _put_labels(client, analyse_id, [{"name": "CNI"}]).json()["classification"]["labels"][0]
    if names:
        assert _upload(client, analyse_id, label["id"], *names).status_code == 201
    return analyse_id, label


def test_a_label_has_several_example_documents(client: TestClient) -> None:
    analyse_id, label = _label_with_examples(client, "recto.png", "verso.png")

    listed = client.get(f"/api/analyses/{analyse_id}/classification/labels/{label['id']}/examples").json()
    in_analyse = _labels(client, analyse_id)[0]["examples"]

    assert [e["name"] for e in listed] == ["recto.png", "verso.png"]
    assert [e["id"] for e in in_analyse] == [e["id"] for e in listed]
    assert listed[0]["kind"] == "image" and listed[0]["content_type"] == "image/png" and listed[0]["size"] > 0
    file = client.get(f"/api/analyses/{analyse_id}/classification/labels/{label['id']}/examples/{listed[0]['id']}/file")
    assert file.status_code == 200 and file.headers["content-type"] == "image/png"


def test_a_pdf_example_is_accepted_and_other_formats_are_refused(client: TestClient) -> None:
    analyse_id, label = _label_with_examples(client)

    assert _upload(client, analyse_id, label["id"], "modele.pdf", content_type="application/pdf").status_code == 201
    refused = _upload(client, analyse_id, label["id"], "notes.txt", content_type="text/plain")

    assert refused.status_code == 422 and "notes.txt" in refused.json()["detail"]
    assert [e["kind"] for e in _labels(client, analyse_id)[0]["examples"]] == ["pdf"]


def test_a_label_takes_ten_examples_at_most(client: TestClient) -> None:
    analyse_id, label = _label_with_examples(client, *(f"e{i}.png" for i in range(10)))

    assert _upload(client, analyse_id, label["id"], "de-trop.png").status_code == 422
    assert len(_labels(client, analyse_id)[0]["examples"]) == 10


def test_a_zone_can_be_drawn_on_an_example_and_deleting_it_keeps_the_rectangle(client: TestClient) -> None:
    analyse_id, label = _label_with_examples(client, "recto.png")
    example = _labels(client, analyse_id)[0]["examples"][0]
    zone = {"example_id": example["id"], "x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.4}
    _put_entities(client, analyse_id, [_entity("nom", label_ids=[label["id"]], zones=[zone])])

    assert _entities(client, analyse_id)[0]["zones"] == [zone]

    deleted = client.delete(f"/api/analyses/{analyse_id}/classification/labels/{label['id']}/examples/{example['id']}")

    assert deleted.status_code == 204
    assert _entities(client, analyse_id)[0]["zones"] == [{**zone, "example_id": None}]
    assert _labels(client, analyse_id)[0]["examples"] == []


def test_a_zone_cannot_point_to_an_unknown_example(client: TestClient) -> None:
    analyse_id = _analyse(client)
    zone = {"example_id": str(uuid.uuid4()), "x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.4}

    assert _put_entities(client, analyse_id, [_entity("nom", zones=[zone])]).status_code == 422


def test_removing_a_label_removes_its_examples(client: TestClient) -> None:
    analyse_id, label = _label_with_examples(client, "recto.png")
    example = _labels(client, analyse_id)[0]["examples"][0]

    assert _put_labels(client, analyse_id, []).status_code == 200

    assert client.get(f"/api/analyses/{analyse_id}").json()["classification"]["labels"] == []
    missing = client.get(f"/api/analyses/{analyse_id}/classification/labels/{label['id']}/examples")
    assert missing.status_code == 404 and example["id"]


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


# --- Droits : le créateur et les administrateurs modifient, les autres lisent ---


def _person(suffix: str, *, admin: bool = False):
    from app.core.security.factory import RequestContext

    return RequestContext(
        user_id=f"droits-{suffix}",
        email=f"{suffix}@example.org",
        roles=["admin"] if admin else [],
        is_admin=admin,
        groups=["/dev-tests"],
    )


def _as(person):
    from app.core.security.factory import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: person


def _restore_identity() -> None:
    from app.core.security.factory import get_current_user
    from app.main import app

    app.dependency_overrides.pop(get_current_user, None)


def test_changing_labels_entities_and_examples_needs_the_permission(client: TestClient, without_role) -> None:
    without_role(_person("autre").user_id)
    creator, stranger, admin = _person("createur"), _person("autre"), _person("admin", admin=True)
    try:
        _as(creator)
        analyse_id = _analyse(client)
        label = _put_labels(client, analyse_id, [{"name": "CNI"}]).json()["classification"]["labels"][0]
        assert _upload(client, analyse_id, label["id"], "recto.png").status_code == 201
        example = _labels(client, analyse_id)[0]["examples"][0]
        _put_entities(client, analyse_id, [_entity("nom", label_ids=[label["id"]])])
        base = f"/api/analyses/{analyse_id}"

        _as(stranger)
        assert _put_labels(client, analyse_id, []).status_code == 403
        assert _put_entities(client, analyse_id, []).status_code == 403
        assert _upload(client, analyse_id, label["id"], "autre.png").status_code == 403
        assert client.delete(f"{base}/classification/labels/{label['id']}/examples/{example['id']}").status_code == 403
        assert client.post(f"{base}/classification/labels/restore/{uuid.uuid4()}").status_code == 403
        assert client.post(f"{base}/extraction/entities/restore/{uuid.uuid4()}").status_code == 403
        # La lecture reste ouverte : liste, fichier, et l'analyse elle-même.
        assert client.get(f"{base}/classification/labels/{label['id']}/examples").status_code == 200
        assert (
            client.get(f"{base}/classification/labels/{label['id']}/examples/{example['id']}/file").status_code == 200
        )
        assert client.get(base).status_code == 200
        # Rien n'a bougé.
        assert len(_labels(client, analyse_id)) == 1 and len(_labels(client, analyse_id)[0]["examples"]) == 1

        _as(admin)
        assert _upload(client, analyse_id, label["id"], "admin.png").status_code == 201
        assert _put_entities(client, analyse_id, []).status_code == 200
    finally:
        _restore_identity()
