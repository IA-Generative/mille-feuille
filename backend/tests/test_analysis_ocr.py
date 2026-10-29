import uuid

from fastapi.testclient import TestClient

INTERNAL = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


def make_analyse(client: TestClient) -> str:
    return client.post("/api/analyses", json={"name": f"OCR {uuid.uuid4().hex[:6]}", "description": "T"}).json()["id"]


def url(analyse_id: str, suffix: str = "") -> str:
    return f"/api/analyses/{analyse_id}/ocr-settings{suffix}"


def test_an_analyse_starts_with_the_platform_model_and_no_history(client: TestClient) -> None:
    body = client.get(url(make_analyse(client))).json()

    assert body == {"settings": {"caption_model": None}, "versions": []}


def test_the_model_is_saved_and_the_previous_settings_go_to_the_history(client: TestClient) -> None:
    analyse_id = make_analyse(client)

    first = client.put(url(analyse_id), json={"caption_model": "pixtral-12b"}).json()
    second = client.put(url(analyse_id), json={"caption_model": "gpt-4o"}).json()

    assert first["settings"] == {"caption_model": "pixtral-12b"}
    assert [v["content"] for v in first["versions"]] == [{"caption_model": None}]
    assert second["settings"] == {"caption_model": "gpt-4o"}
    assert [v["content"]["caption_model"] for v in second["versions"]] == ["pixtral-12b", None]


def test_saving_the_same_settings_adds_no_version(client: TestClient) -> None:
    analyse_id = make_analyse(client)
    client.put(url(analyse_id), json={"caption_model": "pixtral-12b"})

    body = client.put(url(analyse_id), json={"caption_model": "pixtral-12b"}).json()

    assert len(body["versions"]) == 1


def test_a_version_can_be_restored_and_the_current_settings_become_a_version(client: TestClient) -> None:
    analyse_id = make_analyse(client)
    client.put(url(analyse_id), json={"caption_model": "pixtral-12b"})
    body = client.put(url(analyse_id), json={"caption_model": "gpt-4o"}).json()
    pixtral = next(v for v in body["versions"] if v["content"]["caption_model"] == "pixtral-12b")

    restored = client.post(url(analyse_id, f"/restore/{pixtral['id']}")).json()

    assert restored["settings"] == {"caption_model": "pixtral-12b"}
    assert any(v["content"]["caption_model"] == "gpt-4o" for v in restored["versions"])


def test_restoring_an_unknown_version_is_a_404(client: TestClient) -> None:
    assert client.post(url(make_analyse(client), f"/restore/{uuid.uuid4()}")).status_code == 404


def test_an_unknown_analyse_is_a_404(client: TestClient) -> None:
    assert client.get(url(str(uuid.uuid4()))).status_code == 404


def test_the_worker_reads_the_model_of_the_analyse_of_the_dossier(client: TestClient) -> None:
    analyse_id = make_analyse(client)
    client.put(url(analyse_id), json={"caption_model": "pixtral-12b"})
    dossier_id = client.post("/api/dossiers", json={"name": "D", "analyse_id": analyse_id}).json()["id"]

    response = client.get(f"/api/internal/dossiers/{dossier_id}/ocr-settings", headers=INTERNAL)

    assert response.json() == {"caption_model": "pixtral-12b"}


def test_a_dossier_without_analyse_gets_the_platform_defaults(client: TestClient) -> None:
    dossier_id = client.post("/api/dossiers", json={"name": "À ranger"}).json()["id"]

    response = client.get(f"/api/internal/dossiers/{dossier_id}/ocr-settings", headers=INTERNAL)

    assert response.json() == {"caption_model": None}


def test_the_internal_route_needs_the_worker_token_and_a_known_dossier(client: TestClient) -> None:
    dossier_id = str(uuid.uuid4())
    assert client.get(f"/api/internal/dossiers/{dossier_id}/ocr-settings").status_code in (401, 403, 422)
    assert client.get(f"/api/internal/dossiers/{dossier_id}/ocr-settings", headers=INTERNAL).status_code == 404
