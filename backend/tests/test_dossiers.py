import uuid

from fastapi.testclient import TestClient


def _create_analyse(client: TestClient, name: str = "Analyse dossier test") -> str:
    return client.post("/api/analyses", json={"name": name, "description": "Test"}).json()["id"]


def test_dossier_requires_an_existing_analyse(client: TestClient) -> None:
    response = client.post(
        "/api/dossiers",
        json={"name": "Dossier orphelin", "analyse_id": str(uuid.uuid4())},
    )
    assert response.status_code == 400


def test_list_dossiers_is_paginated(client: TestClient) -> None:
    analyse_id = _create_analyse(client, "Analyse pagination dossiers")
    for i in range(5):
        client.post(
            "/api/dossiers",
            json={"name": f"Dossier pagination {i}", "analyse_id": analyse_id},
        )

    first_page = client.get("/api/dossiers", params={"page": 1, "page_size": 2}).json()
    assert len(first_page["items"]) == 2
    assert first_page["page"] == 1
    assert first_page["page_size"] == 2
    assert first_page["total"] >= 5

    second_page = client.get("/api/dossiers", params={"page": 2, "page_size": 2}).json()
    first_ids = {d["id"] for d in first_page["items"]}
    second_ids = {d["id"] for d in second_page["items"]}
    assert first_ids.isdisjoint(second_ids)


def test_create_dossier_and_launch_lifecycle(client: TestClient) -> None:
    analyse_id = _create_analyse(client)

    dossier = client.post("/api/dossiers", json={"name": "Dossier 2026-0001", "analyse_id": analyse_id}).json()
    assert dossier["status"] == "en_attente"
    assert dossier["analyse_version"] == "v1"

    dossier = client.post(f"/api/dossiers/{dossier['id']}/launch").json()
    assert dossier["status"] == "en_cours"
    assert dossier["started_at"] is not None
    kinds = {step["kind"] for step in dossier["execution_steps"]}
    assert kinds == {"classification", "extraction"}

    dossier = client.post(f"/api/dossiers/{dossier['id']}/stop").json()
    assert dossier["status"] == "arrêté"
    assert dossier["ended_at"] is not None


def test_launch_adds_one_step_per_agent(client: TestClient) -> None:
    analyse_id = _create_analyse(client, "Analyse avec agent")
    client.post(
        f"/api/analyses/{analyse_id}/agents",
        json={
            "name": "Cohérence",
            "prompt": "Vérifie la cohérence.",
            "tools": [],
            "output": True,
        },
    )

    dossier = client.post("/api/dossiers", json={"name": "Dossier avec agent", "analyse_id": analyse_id}).json()
    dossier = client.post(f"/api/dossiers/{dossier['id']}/launch").json()

    agent_steps = [step for step in dossier["execution_steps"] if step["kind"] == "agent"]
    assert len(agent_steps) == 1
    assert agent_steps[0]["label"] == "Cohérence"


def test_document_upload_and_label(client: TestClient) -> None:
    analyse_id = _create_analyse(client, "Analyse documents")
    dossier = client.post("/api/dossiers", json={"name": "Dossier documents", "analyse_id": analyse_id}).json()

    dossier = client.post(
        f"/api/dossiers/{dossier['id']}/documents",
        files=[("files", ("cni_recto.jpg", b"fake-bytes", "image/jpeg"))],
    ).json()
    document = dossier["documents"][0]
    assert document["name"] == "cni_recto.jpg"
    assert document["mimetype"] == "image/jpeg"
    assert document["s3_key"].startswith(f"dossiers/{dossier['id']}/")
    assert document["label"] is None

    updated = client.put(
        f"/api/dossiers/{dossier['id']}/documents/{document['id']}/label",
        json={"label": "CNI"},
    ).json()
    assert updated["label"] == "CNI"


def test_document_upload_dispatches_text_extraction(client: TestClient, monkeypatch) -> None:
    dispatched: list[str] = []
    monkeypatch.setattr("app.routers.dossiers.dispatch_text_extraction", dispatched.append)

    analyse_id = _create_analyse(client, "Analyse dispatch")
    dossier = client.post("/api/dossiers", json={"name": "Dossier dispatch", "analyse_id": analyse_id}).json()
    dossier = client.post(
        f"/api/dossiers/{dossier['id']}/documents",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
    ).json()
    document = dossier["documents"][0]

    assert document["text_extraction_status"] == "en_attente"
    assert document["text_extraction_error"] is None
    assert dispatched == [document["id"]]


def test_internal_set_extraction_status(client: TestClient) -> None:
    analyse_id = _create_analyse(client, "Analyse statut extraction")
    dossier = client.post("/api/dossiers", json={"name": "Dossier statut", "analyse_id": analyse_id}).json()
    dossier = client.post(
        f"/api/dossiers/{dossier['id']}/documents",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
    ).json()
    document_id = dossier["documents"][0]["id"]
    headers = {"X-App-Token": "dev-only-worker-token-not-for-prod"}

    started = client.put(
        f"/api/internal/documents/{document_id}/extraction-status",
        json={"status": "en_cours"},
        headers=headers,
    ).json()
    assert started["text_extraction_status"] == "en_cours"

    failed = client.put(
        f"/api/internal/documents/{document_id}/extraction-status",
        json={"status": "échec", "error": "PDF corrompu"},
        headers=headers,
    ).json()
    assert failed["text_extraction_status"] == "échec"
    assert failed["text_extraction_error"] == "PDF corrompu"


def test_internal_get_document_returns_s3_key_for_worker(client: TestClient) -> None:
    analyse_id = _create_analyse(client, "Analyse document interne")
    dossier = client.post("/api/dossiers", json={"name": "Dossier interne", "analyse_id": analyse_id}).json()
    dossier = client.post(
        f"/api/dossiers/{dossier['id']}/documents",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
    ).json()
    document = dossier["documents"][0]

    response = client.get(
        f"/api/internal/documents/{document['id']}",
        headers={"X-App-Token": "dev-only-worker-token-not-for-prod"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == document["id"]
    assert body["s3_key"] == document["s3_key"]
    assert body["mimetype"] == "application/pdf"
    assert body["pages"] == []


def test_conversation_and_message_lifecycle(client: TestClient) -> None:
    analyse_id = _create_analyse(client, "Analyse conversation")
    dossier = client.post("/api/dossiers", json={"name": "Dossier chat", "analyse_id": analyse_id}).json()
    dossier_id = dossier["id"]

    conversation = client.post(f"/api/dossiers/{dossier_id}/conversations").json()
    assert conversation["dossier_id"] == dossier_id
    assert conversation["user_id"] == "dev-user"
    assert "messages" not in conversation
    messages_url = f"/api/dossiers/{dossier_id}/conversations/{conversation['id']}/messages"
    assert client.get(messages_url).json() == {"items": [], "has_more": False}

    message = client.post(messages_url, json={"content": "Quel est le statut du dossier ?"}).json()
    assert message["role"] == "user"
    assert message["content"] == "Quel est le statut du dossier ?"
    assert [m["id"] for m in client.get(messages_url).json()["items"]] == [message["id"]]

    listed = client.get(f"/api/dossiers/{dossier_id}/conversations").json()["items"]
    assert len(listed) == 1
    assert listed[0]["id"] == conversation["id"]


def test_create_conversation_is_idempotent_per_user(client: TestClient) -> None:
    # "Aller sur un dossier" crée une conversation une seule fois par
    # utilisateur : cliquer/recharger plusieurs fois ne doit pas en
    # dupliquer une nouvelle à chaque fois.
    analyse_id = _create_analyse(client, "Analyse conversation idempotente")
    dossier_id = client.post("/api/dossiers", json={"name": "Dossier idempotent", "analyse_id": analyse_id}).json()[
        "id"
    ]

    first = client.post(f"/api/dossiers/{dossier_id}/conversations").json()
    second = client.post(f"/api/dossiers/{dossier_id}/conversations").json()
    assert first["id"] == second["id"]

    listed = client.get(f"/api/dossiers/{dossier_id}/conversations").json()["items"]
    assert len(listed) == 1


def test_conversation_is_private_to_its_user(client: TestClient) -> None:
    """Une conversation appartient à un (dossier, utilisateur) : un autre
    utilisateur ne doit ni la voir dans sa liste, ni pouvoir y écrire, même
    en connaissant son id."""
    from app.core.security.factory import RequestContext, get_current_user
    from app.main import app

    analyse_id = _create_analyse(client, "Analyse conversation privée")
    dossier_id = client.post("/api/dossiers", json={"name": "Dossier privé", "analyse_id": analyse_id}).json()["id"]

    owner_conversation = client.post(f"/api/dossiers/{dossier_id}/conversations").json()
    client.post(
        f"/api/dossiers/{dossier_id}/conversations/{owner_conversation['id']}/messages",
        json={"content": "Message du propriétaire"},
    )

    def as_other_user() -> RequestContext:
        return RequestContext(
            user_id="other-user", email="other@example.com", roles=[], is_admin=False, groups=["/dev-tests"]
        )

    app.dependency_overrides[get_current_user] = as_other_user
    try:
        # Pas dans la liste de l'autre utilisateur...
        other_listed = client.get(f"/api/dossiers/{dossier_id}/conversations").json()["items"]
        assert other_listed == []

        # ...et une nouvelle conversation pour cet utilisateur, pas la même.
        other_conversation = client.post(f"/api/dossiers/{dossier_id}/conversations").json()
        assert other_conversation["id"] != owner_conversation["id"]
        assert other_conversation["user_id"] == "other-user"

        # Impossible d'écrire dans celle du propriétaire en devinant son id.
        response = client.post(
            f"/api/dossiers/{dossier_id}/conversations/{owner_conversation['id']}/messages",
            json={"content": "Tentative d'intrusion"},
        )
        assert response.status_code == 404
    finally:
        del app.dependency_overrides[get_current_user]

    # Le message de l'autre utilisateur n'a pas fuité dans la conversation du propriétaire.
    owner_view = client.get(f"/api/dossiers/{dossier_id}/conversations").json()["items"]
    assert len(owner_view) == 1
    owner_messages = client.get(f"/api/dossiers/{dossier_id}/conversations/{owner_view[0]['id']}/messages").json()[
        "items"
    ]
    assert [m["content"] for m in owner_messages] == ["Message du propriétaire"]


def test_conversation_model_can_be_chosen(client: TestClient) -> None:
    analyse_id = _create_analyse(client, "Analyse modèle conversation")
    dossier_id = client.post("/api/dossiers", json={"name": "Dossier modèle", "analyse_id": analyse_id}).json()["id"]

    conversation = client.post(f"/api/dossiers/{dossier_id}/conversations").json()
    assert conversation["model"] is None

    updated = client.put(
        f"/api/dossiers/{dossier_id}/conversations/{conversation['id']}/model",
        json={"model": "gpt-4o"},
    ).json()
    assert updated["model"] == "gpt-4o"

    listed = client.get(f"/api/dossiers/{dossier_id}/conversations").json()["items"]
    assert listed[0]["model"] == "gpt-4o"


def test_delete_conversation_only_removes_the_conversation(client: TestClient) -> None:
    """Supprimer une conversation ne doit toucher qu'elle (et ses messages) :
    le dossier et ses documents restent intacts."""
    analyse_id = _create_analyse(client, "Analyse suppression conversation")
    dossier_id = client.post("/api/dossiers", json={"name": "Dossier à garder", "analyse_id": analyse_id}).json()["id"]
    client.post(
        f"/api/dossiers/{dossier_id}/documents",
        files={"files": ("note.txt", b"contenu", "text/plain")},
    )

    conversation = client.post(f"/api/dossiers/{dossier_id}/conversations").json()
    client.post(
        f"/api/dossiers/{dossier_id}/conversations/{conversation['id']}/messages",
        json={"content": "Un message"},
    )

    response = client.delete(f"/api/dossiers/{dossier_id}/conversations/{conversation['id']}")
    assert response.status_code == 204

    assert client.get(f"/api/dossiers/{dossier_id}/conversations").json()["items"] == []

    dossier = client.get(f"/api/dossiers/{dossier_id}").json()
    assert dossier["id"] == dossier_id
    assert len(dossier["documents"]) == 1


def test_delete_conversation_is_private_to_its_user(client: TestClient) -> None:
    """Un autre utilisateur ne doit pas pouvoir supprimer la conversation
    d'un autre, même en devinant son id."""
    from app.core.security.factory import RequestContext, get_current_user
    from app.main import app

    analyse_id = _create_analyse(client, "Analyse suppression privée")
    dossier_id = client.post("/api/dossiers", json={"name": "Dossier privé 2", "analyse_id": analyse_id}).json()["id"]
    owner_conversation = client.post(f"/api/dossiers/{dossier_id}/conversations").json()

    def as_other_user() -> RequestContext:
        return RequestContext(
            user_id="other-user", email="other@example.com", roles=[], is_admin=False, groups=["/dev-tests"]
        )

    app.dependency_overrides[get_current_user] = as_other_user
    try:
        response = client.delete(f"/api/dossiers/{dossier_id}/conversations/{owner_conversation['id']}")
        assert response.status_code == 404
    finally:
        del app.dependency_overrides[get_current_user]

    owner_view = client.get(f"/api/dossiers/{dossier_id}/conversations").json()["items"]
    assert len(owner_view) == 1
    assert owner_view[0]["id"] == owner_conversation["id"]


INTERNAL_HEADERS = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


def test_internal_routes_require_app_token(client: TestClient) -> None:
    response = client.post(f"/api/internal/execution-steps/{uuid.uuid4()}/logs", json={"message": "hello"})
    assert response.status_code in (401, 422)  # 422 si le header est simplement absent

    response = client.post(
        f"/api/internal/execution-steps/{uuid.uuid4()}/logs",
        json={"message": "hello"},
        headers={"X-App-Token": "not-a-valid-token"},
    )
    assert response.status_code == 401


def test_execution_step_logs_and_completion(client: TestClient) -> None:
    analyse_id = _create_analyse(client, "Analyse logs")
    dossier = client.post("/api/dossiers", json={"name": "Dossier logs", "analyse_id": analyse_id}).json()
    dossier = client.post(f"/api/dossiers/{dossier['id']}/launch").json()
    step_id = dossier["execution_steps"][0]["id"]

    step = client.post(
        f"/api/internal/execution-steps/{step_id}/logs",
        json={"level": "info", "message": "Lecture du document..."},
        headers=INTERNAL_HEADERS,
    ).json()
    assert len(step["logs"]) == 1
    assert step["logs"][0]["message"] == "Lecture du document..."

    step = client.post(
        f"/api/internal/execution-steps/{step_id}/complete",
        json={"status": "terminé", "output": "CNI (confiance : 96%)"},
        headers=INTERNAL_HEADERS,
    ).json()
    assert step["status"] == "terminé"
    assert step["output"] == "CNI (confiance : 96%)"
    assert step["ended_at"] is not None


def _create_page(client: TestClient, document_id: str, page_number: int, content: str) -> dict:
    return client.post(
        f"/api/internal/documents/{document_id}/pages",
        json={
            "page_number": page_number,
            "width": 1000,
            "height": 1400,
            "content": content,
        },
        headers=INTERNAL_HEADERS,
    ).json()


def _create_bbox(client: TestClient, page_id: str, **coords) -> dict:
    return client.post(
        f"/api/internal/pages/{page_id}/bounding-boxes",
        json=coords,
        headers=INTERNAL_HEADERS,
    ).json()


def test_page_screenshot_is_relayed_through_the_backend(client: TestClient) -> None:
    from app.connectors import s3_connector

    analyse_id = _create_analyse(client, "Analyse capture")
    dossier = client.post("/api/dossiers", json={"name": "Dossier capture", "analyse_id": analyse_id}).json()
    dossier = client.post(
        f"/api/dossiers/{dossier['id']}/documents",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
    ).json()
    document_id = dossier["documents"][0]["id"]

    page_without_screenshot = client.post(
        f"/api/internal/documents/{document_id}/pages",
        json={"page_number": 1},
        headers=INTERNAL_HEADERS,
    ).json()
    assert page_without_screenshot["has_screenshot"] is False
    response = client.get(
        f"/api/dossiers/{dossier['id']}/documents/{document_id}/pages/{page_without_screenshot['id']}/screenshot"
    )
    assert response.status_code == 404

    screenshot_key = f"screenshots/{document_id}/page-1.png"
    s3_connector.upload(screenshot_key, b"fake-png-bytes", "image/png")
    page = client.post(
        f"/api/internal/documents/{document_id}/pages",
        json={"page_number": 2, "screenshot_key": screenshot_key},
        headers=INTERNAL_HEADERS,
    ).json()
    assert page["has_screenshot"] is True
    # Ni la clé S3 ni une URL signée ne sont exposées : juste un booléen.
    assert "screenshot_key" not in page

    response = client.get(f"/api/dossiers/{dossier['id']}/documents/{document_id}/pages/{page['id']}/screenshot")
    assert response.status_code == 200
    assert response.content == b"fake-png-bytes"
    assert response.headers["content-type"] == "image/png"


def test_document_page_view_exposes_text_and_boxes(client: TestClient) -> None:
    analyse_id = _create_analyse(client, "Analyse lecture page")
    dossier = client.post("/api/dossiers", json={"name": "Dossier lecture page", "analyse_id": analyse_id}).json()
    dossier = client.post(
        f"/api/dossiers/{dossier['id']}/documents",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
    ).json()
    document_id = dossier["documents"][0]["id"]
    page = _create_page(client, document_id, 3, "REPUBLIQUE FRANCAISE Carte nationale d'identité")
    bbox = _create_bbox(client, page["id"], x_min=0.1, y_min=0.2, x_max=0.6, y_max=0.3)

    view = client.get(f"/api/dossiers/{dossier['id']}/documents/{document_id}/pages/{page['id']}").json()
    assert view["page_number"] == 3
    assert view["content"] == "REPUBLIQUE FRANCAISE Carte nationale d'identité"
    assert view["document_name"] == "cni.pdf"
    assert view["has_screenshot"] is False
    assert [(b["id"], b["document_page_id"]) for b in view["bounding_boxes"]] == [(bbox["id"], page["id"])]

    missing = client.get(
        f"/api/dossiers/{dossier['id']}/documents/{document_id}/pages/00000000-0000-0000-0000-000000000000"
    )
    assert missing.status_code == 404


def test_classification_prediction_linked_to_one_page_and_label(
    client: TestClient,
) -> None:
    analyse_id = _create_analyse(client, "Analyse classification")
    analyse = client.get(f"/api/analyses/{analyse_id}").json()
    label = client.put(
        f"/api/analyses/{analyse_id}/classification/labels",
        json={"labels": [{"name": "CNI", "definition": "Carte nationale d'identité."}]},
    ).json()["classification"]["labels"][0]

    dossier = client.post(
        "/api/dossiers",
        json={"name": "Dossier classification", "analyse_id": analyse_id},
    ).json()
    dossier = client.post(
        f"/api/dossiers/{dossier['id']}/documents",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
    ).json()
    document_id = dossier["documents"][0]["id"]

    page = _create_page(client, document_id, 1, "REPUBLIQUE FRANCAISE ...")
    assert page["predictions"] == []
    bbox = _create_bbox(client, page["id"], x_min=0.1, y_min=0.1, x_max=0.9, y_max=0.5)

    prediction = client.post(
        f"/api/internal/pages/{page['id']}/predictions",
        json={
            "kind": "label",
            "name": "CNI",
            "value": "CNI",
            "confidence": 0.96,
            "label_definition_id": label["id"],
            "bounding_box_ids": [bbox["id"]],
        },
        headers=INTERNAL_HEADERS,
    ).json()
    # Une classification reste "simplement liée à une page" : l'ensemble n'a
    # qu'un seul élément.
    assert [p["id"] for p in prediction["pages"]] == [page["id"]]
    assert [b["id"] for b in prediction["bounding_boxes"]] == [bbox["id"]]
    assert prediction["label_definition_id"] == label["id"]
    assert prediction["entity_definition_id"] is None
    assert prediction["validations"] == []
    assert analyse["id"] == analyse_id  # sanity: le label créé plus haut appartient bien à cette analyse

    dossier = client.get(f"/api/dossiers/{dossier['id']}").json()
    fetched_page = dossier["documents"][0]["pages"][0]
    assert fetched_page["predictions"][0]["name"] == "CNI"
    # La bbox de la prédiction est aussi rattachée à la page (nouvelle table
    # dédiée) : même bbox visible aux deux endroits.
    assert [b["id"] for b in fetched_page["bounding_boxes"]] == [bbox["id"]]

    validated = client.put(
        f"/api/dossiers/{dossier['id']}/documents/{document_id}/pages/{page['id']}"
        f"/predictions/{prediction['id']}/validations",
        json={
            "status": "corrigé",
            "corrected_value": "Carte Nationale d'Identité",
            "bounding_box": {"x_min": 0.12, "y_min": 0.1, "x_max": 0.9, "y_max": 0.5},
        },
    ).json()
    assert validated["status"] == "corrigé"
    assert validated["corrected_value"] == "Carte Nationale d'Identité"
    assert validated["validator_user_id"] == "dev-user"
    # La correction crée sa propre bbox, distincte de celle de la prédiction
    # d'origine (l'historique reste intact).
    assert validated["bounding_box"]["id"] != bbox["id"]
    assert validated["bounding_box"]["x_min"] == 0.12


def test_entity_prediction_can_span_several_pages_and_bboxes(
    client: TestClient,
) -> None:
    analyse_id = _create_analyse(client, "Analyse extraction")
    entity = client.put(
        f"/api/analyses/{analyse_id}/extraction/entities",
        json={"entities": [{"name": "adresse", "definition": "Adresse postale.", "type": "texte"}]},
    ).json()["extraction"]["entities"][0]

    dossier = client.post("/api/dossiers", json={"name": "Dossier extraction", "analyse_id": analyse_id}).json()
    dossier = client.post(
        f"/api/dossiers/{dossier['id']}/documents",
        files=[("files", ("avis.pdf", b"fake-bytes", "application/pdf"))],
    ).json()
    document_id = dossier["documents"][0]["id"]

    page1 = _create_page(client, document_id, 1, "... suite page suivante")
    page2 = _create_page(client, document_id, 2, "12 rue de la République, 75011 Paris")
    bbox1 = _create_bbox(client, page1["id"], x_min=0.1, y_min=0.8, x_max=0.9, y_max=0.95)
    bbox2 = _create_bbox(client, page2["id"], x_min=0.1, y_min=0.05, x_max=0.9, y_max=0.2)

    prediction = client.post(
        f"/api/internal/pages/{page1['id']}/predictions",
        json={
            "kind": "entity",
            "name": "adresse",
            "value": "12 rue de la République, 75011 Paris",
            "entity_definition_id": entity["id"],
            "page_ids": [page2["id"]],
            "bounding_box_ids": [bbox1["id"], bbox2["id"]],
        },
        headers=INTERNAL_HEADERS,
    ).json()
    assert {p["id"] for p in prediction["pages"]} == {page1["id"], page2["id"]}
    assert {b["id"] for b in prediction["bounding_boxes"]} == {bbox1["id"], bbox2["id"]}
    assert prediction["entity_definition_id"] == entity["id"]
    assert prediction["label_definition_id"] is None

    # La prédiction apparaît sur ses deux pages, pas seulement la première.
    dossier = client.get(f"/api/dossiers/{dossier['id']}").json()
    pages = dossier["documents"][0]["pages"]
    assert all(prediction["id"] in [p["id"] for p in page["predictions"]] for page in pages)


def test_dossier_results_paginated_with_breakdown_per_file(client: TestClient) -> None:
    analyse_id = _create_analyse(client, "Analyse résultats")
    dossier = client.post("/api/dossiers", json={"name": "Dossier résultats", "analyse_id": analyse_id}).json()
    dossier = client.post(
        f"/api/dossiers/{dossier['id']}/documents",
        files=[
            ("files", ("a.pdf", b"fake-bytes", "application/pdf")),
            ("files", ("b.pdf", b"fake-bytes", "application/pdf")),
        ],
    ).json()
    dossier_id = dossier["id"]
    doc_a, doc_b = (d["id"] for d in sorted(dossier["documents"], key=lambda d: d["name"]))
    a1, a2 = _create_page(client, doc_a, 1, "a1"), _create_page(client, doc_a, 2, "a2")
    b1 = _create_page(client, doc_b, 1, "b1")

    def predict(page: dict, kind: str, name: str, value: str, **extra) -> None:
        response = client.post(
            f"/api/internal/pages/{page['id']}/predictions",
            json={"kind": kind, "name": name, "value": value, "confidence": 0.9, **extra},
            headers=INTERNAL_HEADERS,
        )
        assert response.status_code == 201, response.text

    predict(a1, "label", "CNI", "CNI")
    predict(a2, "label", "RIB", "RIB")
    predict(b1, "label", "CNI", "CNI")
    bbox = _create_bbox(client, a1["id"], x_min=0.1, y_min=0.2, x_max=0.6, y_max=0.3)
    predict(a1, "entity", "adresse", "12 rue X", page_ids=[a2["id"]], bounding_box_ids=[bbox["id"]])
    predict(b1, "entity", "nom", "Dupont")

    breakdown = client.get(f"/api/dossiers/{dossier_id}/results/breakdown").json()
    assert [
        (r["document_name"], r["page_count"], r["classified_page_count"], r["entity_count"]) for r in breakdown
    ] == [
        ("a.pdf", 2, 2, 1),
        ("b.pdf", 1, 1, 1),
    ]

    first = client.get(f"/api/dossiers/{dossier_id}/results", params={"kind": "label", "page_size": 2}).json()
    assert (first["total"], first["pages"], len(first["items"])) == (3, 2, 2)
    second = client.get(
        f"/api/dossiers/{dossier_id}/results", params={"kind": "label", "page_size": 2, "page": 2}
    ).json()
    assert len(second["items"]) == 1
    labels = first["items"] + second["items"]
    assert sorted((r["document_name"], r["name"]) for r in labels) == [
        ("a.pdf", "CNI"),
        ("a.pdf", "RIB"),
        ("b.pdf", "CNI"),
    ]

    entities = client.get(f"/api/dossiers/{dossier_id}/results", params={"kind": "entity"}).json()
    address = next(r for r in entities["items"] if r["name"] == "adresse")
    assert (address["document_name"], [p["page_number"] for p in address["pages"]], address["value"]) == (
        "a.pdf",
        [1, 2],
        "12 rue X",
    )
    assert [(b["id"], b["document_page_id"]) for b in address["bounding_boxes"]] == [(bbox["id"], a1["id"])]
    assert entities["total"] == 2


def test_assistant_message_with_sources(client: TestClient) -> None:
    analyse_id = _create_analyse(client, "Analyse sources")
    dossier = client.post("/api/dossiers", json={"name": "Dossier sources", "analyse_id": analyse_id}).json()
    dossier_id = dossier["id"]
    dossier = client.post(
        f"/api/dossiers/{dossier_id}/documents",
        files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))],
    ).json()
    document_id = dossier["documents"][0]["id"]
    page = _create_page(client, document_id, 1, "REPUBLIQUE FRANCAISE ...")
    bbox = _create_bbox(client, page["id"], x_min=0.1, y_min=0.1, x_max=0.9, y_max=0.5)
    conversation = client.post(f"/api/dossiers/{dossier_id}/conversations").json()

    message = client.post(
        f"/api/internal/conversations/{conversation['id']}/messages",
        json={
            "content": "Le document est une CNI.",
            "sources": [
                # À minima : le document entier.
                {"dossier_document_id": document_id, "excerpt": "REPUBLIQUE FRANCAISE"},
                # Plus précis : un ensemble de pages, ou de bbox.
                {"dossier_document_id": document_id, "page_ids": [page["id"]]},
                {"dossier_document_id": document_id, "bounding_box_ids": [bbox["id"]]},
            ],
        },
        headers=INTERNAL_HEADERS,
    ).json()
    assert message["role"] == "assistant"
    assert len(message["sources"]) == 3
    assert message["sources"][0]["dossier_document_id"] == document_id
    assert message["sources"][0]["pages"] == []
    assert [p["id"] for p in message["sources"][1]["pages"]] == [page["id"]]
    assert [b["id"] for b in message["sources"][2]["bounding_boxes"]] == [bbox["id"]]


def test_execution_stream_sends_terminal_state(client: TestClient) -> None:
    analyse_id = _create_analyse(client, "Analyse SSE")
    dossier = client.post("/api/dossiers", json={"name": "Dossier SSE", "analyse_id": analyse_id}).json()
    dossier = client.post(f"/api/dossiers/{dossier['id']}/launch").json()
    for step in dossier["execution_steps"]:
        client.post(
            f"/api/internal/execution-steps/{step['id']}/complete",
            json={"status": "terminé", "output": "ok"},
            headers=INTERNAL_HEADERS,
        )
    # Compléter la dernière étape fait passer le Dossier lui-même à
    # "terminé" (toutes les étapes sont dans un état terminal).
    dossier = client.get(f"/api/dossiers/{dossier['id']}").json()
    assert dossier["status"] == "terminé"

    with client.stream("GET", f"/api/dossiers/{dossier['id']}/stream") as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())
    assert "execution-update" in body
    assert "termin" in body  # "terminé", échappé ou non selon l'encodage JSON


def _create_conversation_with_message(client: TestClient, dossier_name: str) -> tuple[str, str, str]:
    analyse_id = _create_analyse(client, f"Analyse {dossier_name}")
    dossier_id = client.post("/api/dossiers", json={"name": dossier_name, "analyse_id": analyse_id}).json()["id"]
    conversation = client.post(f"/api/dossiers/{dossier_id}/conversations").json()
    message = client.post(
        f"/api/dossiers/{dossier_id}/conversations/{conversation['id']}/messages",
        json={"content": "Un message"},
    ).json()
    return dossier_id, conversation["id"], message["id"]


def test_message_feedback_lifecycle(client: TestClient) -> None:
    dossier_id, conversation_id, message_id = _create_conversation_with_message(client, "Dossier retour")

    messages_url = f"/api/dossiers/{dossier_id}/conversations/{conversation_id}/messages"
    assert client.get(messages_url).json()["items"][0]["feedback"] is None

    message = client.put(
        f"/api/dossiers/{dossier_id}/conversations/{conversation_id}/messages/{message_id}/feedback",
        json={
            "value": "down",
            "reasons": ["incorrect_answer", "not_useful"],
            "comment": "Pas la bonne réponse",
        },
    ).json()
    feedback = message["feedback"]
    assert feedback["value"] == "down"
    assert sorted(feedback["reasons"]) == ["incorrect_answer", "not_useful"]
    assert feedback["comment"] == "Pas la bonne réponse"

    # Re-soumission : mise à jour du même retour, pas de doublon.
    message = client.put(
        f"/api/dossiers/{dossier_id}/conversations/{conversation_id}/messages/{message_id}/feedback",
        json={"value": "up"},
    ).json()
    feedback = message["feedback"]
    assert feedback["value"] == "up"
    assert feedback["reasons"] == []
    assert feedback["comment"] is None

    message = client.delete(
        f"/api/dossiers/{dossier_id}/conversations/{conversation_id}/messages/{message_id}/feedback"
    ).json()
    assert message["feedback"] is None
    assert client.get(messages_url).json()["items"][0]["feedback"] is None


def test_messages_are_paginated_by_cursor(client: TestClient) -> None:
    analyse_id = _create_analyse(client, "Analyse pagination messages")
    dossier_id = client.post("/api/dossiers", json={"name": "Dossier pagination", "analyse_id": analyse_id}).json()[
        "id"
    ]
    conversation = client.post(f"/api/dossiers/{dossier_id}/conversations").json()
    url = f"/api/dossiers/{dossier_id}/conversations/{conversation['id']}/messages"
    for index in range(5):
        client.post(url, json={"content": f"Message {index}"})

    # Sans curseur : les plus récents, en ordre chronologique.
    latest = client.get(url, params={"limit": 2}).json()
    assert [m["content"] for m in latest["items"]] == ["Message 3", "Message 4"]
    assert latest["has_more"] is True

    # Curseur : les messages qui précèdent le plus ancien déjà chargé.
    older = client.get(url, params={"limit": 2, "before": latest["items"][0]["id"]}).json()
    assert [m["content"] for m in older["items"]] == ["Message 1", "Message 2"]
    assert older["has_more"] is True

    oldest = client.get(url, params={"limit": 2, "before": older["items"][0]["id"]}).json()
    assert [m["content"] for m in oldest["items"]] == ["Message 0"]
    assert oldest["has_more"] is False


def test_feedback_is_private_to_its_user(client: TestClient) -> None:
    from app.core.security.factory import RequestContext, get_current_user
    from app.main import app

    dossier_id, conversation_id, message_id = _create_conversation_with_message(client, "Dossier retour privé")

    def as_other_user() -> RequestContext:
        return RequestContext(
            user_id="other-user", email="other@example.com", roles=[], is_admin=False, groups=["/dev-tests"]
        )

    app.dependency_overrides[get_current_user] = as_other_user
    try:
        response = client.put(
            f"/api/dossiers/{dossier_id}/conversations/{conversation_id}/messages/{message_id}/feedback",
            json={"value": "up"},
        )
        assert response.status_code == 404
    finally:
        del app.dependency_overrides[get_current_user]


# ---------------------------------------------------------------------------
# Issue #54 : « Dossier à ranger » — suggestion automatique d'analyse
# ---------------------------------------------------------------------------


def test_create_dossier_without_analyse(client: TestClient) -> None:
    """Un dossier peut être créé sans analyse (« à ranger »).
    Le statut de suggestion démarre à en_attente."""
    dossier = client.post("/api/dossiers", json={"name": "Dossier à ranger"}).json()
    assert dossier["analyse_id"] is None
    assert dossier["suggestion_status"] == "en_attente"
    assert dossier["suggested_analyses"] is None


def test_suggest_analysis_dispatches_celery_task(client: TestClient, monkeypatch) -> None:
    """POST /dossiers/{id}/suggest-analysis dispatche la tâche Celery."""
    dossier = client.post("/api/dossiers", json={"name": "Dossier suggestion"}).json()

    dispatched: list[str] = []
    monkeypatch.setattr("app.routers.dossiers.dispatch_analyse_suggestion", lambda d: dispatched.append(d))

    response = client.post(f"/api/dossiers/{dossier['id']}/suggest-analysis")
    assert response.status_code == 200
    assert dispatched == [dossier["id"]]


def test_assign_analyse_to_dossier(client: TestClient) -> None:
    """POST /dossiers/{id}/assign rattache une analyse valide à un dossier
    « à ranger » et récupère la version courante de l'analyse."""
    analyse_id = _create_analyse(client, "Analyse à rattacher")
    dossier = client.post("/api/dossiers", json={"name": "Dossier à assigner"}).json()
    assert dossier["analyse_id"] is None

    response = client.post(f"/api/dossiers/{dossier['id']}/assign", json={"analyse_id": analyse_id})
    assert response.status_code == 200
    body = response.json()
    assert body["analyse_id"] == analyse_id
    assert body["analyse_version"] == "v1"


def test_assign_analyse_404_for_unknown_dossier(client: TestClient) -> None:
    analyse_id = _create_analyse(client, "Analyse 404 assign")
    response = client.post(f"/api/dossiers/{uuid.uuid4()}/assign", json={"analyse_id": analyse_id})
    assert response.status_code == 404


def test_assign_analyse_400_for_unknown_analyse(client: TestClient) -> None:
    dossier = client.post("/api/dossiers", json={"name": "Dossier assign 400"}).json()
    response = client.post(f"/api/dossiers/{dossier['id']}/assign", json={"analyse_id": str(uuid.uuid4())})
    assert response.status_code == 400


def test_internal_set_suggestion_status(client: TestClient) -> None:
    """PUT /internal/dossiers/{id}/suggestion-status met à jour le statut."""
    dossier = client.post("/api/dossiers", json={"name": "Dossier statut suggestion"}).json()

    response = client.put(
        f"/api/internal/dossiers/{dossier['id']}/suggestion-status",
        json={"status": "en_cours"},
        headers=INTERNAL_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["suggestion_status"] == "en_cours"

    response = client.put(
        f"/api/internal/dossiers/{dossier['id']}/suggestion-status",
        json={"status": "échec", "error": "LLM indisponible"},
        headers=INTERNAL_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["suggestion_status"] == "échec"

    # L'erreur est stockée dans summary_error (canal d'erreur partagé) :
    # vérifiable via l'endpoint public qui expose ce champ.
    public = client.get(f"/api/dossiers/{dossier['id']}").json()
    assert public["summary_error"] == "LLM indisponible"


def test_internal_deposit_suggested_analyses(client: TestClient) -> None:
    """POST /internal/dossiers/{id}/suggestions dépose les suggestions du
    worker et passe le statut à terminé."""
    analyse_id = _create_analyse(client, "Analyse suggérée")
    dossier = client.post("/api/dossiers", json={"name": "Dossier dépôt suggestions"}).json()

    suggestions = [
        {"analyse_id": analyse_id, "name": "Analyse suggérée", "score": 0.92, "rationale": "Correspondance forte."},
        {"analyse_id": str(uuid.uuid4()), "name": "Autre analyse", "score": 0.45, "rationale": "Moins pertinent."},
    ]
    response = client.post(
        f"/api/internal/dossiers/{dossier['id']}/suggestions",
        json={"suggestions": suggestions},
        headers=INTERNAL_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["suggestion_status"] == "terminé"
    assert len(body["suggested_analyses"]) == 2
    assert body["suggested_analyses"][0]["analyse_id"] == analyse_id
    assert body["suggested_analyses"][0]["score"] == 0.92


def test_internal_deposit_suggestions_404(client: TestClient) -> None:
    response = client.post(
        f"/api/internal/dossiers/{uuid.uuid4()}/suggestions",
        json={"suggestions": []},
        headers=INTERNAL_HEADERS,
    )
    assert response.status_code == 404


def test_internal_suggestion_routes_require_app_token(client: TestClient) -> None:
    dossier = client.post("/api/dossiers", json={"name": "Dossier token suggestion"}).json()

    # Sans token : 401 (ou 422 si le header est absent selon FastAPI).
    response = client.put(
        f"/api/internal/dossiers/{dossier['id']}/suggestion-status",
        json={"status": "en_cours"},
    )
    assert response.status_code in (401, 422)

    # Mauvais token : 401.
    response = client.put(
        f"/api/internal/dossiers/{dossier['id']}/suggestion-status",
        json={"status": "en_cours"},
        headers={"X-App-Token": "wrong-token"},
    )
    assert response.status_code == 401
