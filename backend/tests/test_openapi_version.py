from importlib.metadata import version

from fastapi.testclient import TestClient


def test_swagger_shows_the_installed_package_version(client: TestClient) -> None:
    served = client.get("/api/openapi.json").json()["info"]["version"]
    assert served != "0.1.0"  # valeur par défaut de FastAPI quand `version` n'est pas renseigné
    assert served == version("mille-feuille-backend")
