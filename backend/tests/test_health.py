from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready(client: TestClient) -> None:
    response = client.get("/api/health/ready")
    body = response.json()
    assert {dep["name"] for dep in body["dependencies"]} == {"postgres", "redis", "s3"}


def test_version_is_public_and_matches_the_package(client: TestClient) -> None:
    response = client.get("/api/version")
    assert response.status_code == 200
    assert response.json()["version"]
