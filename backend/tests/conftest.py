import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    # One event loop for the whole run, via the `with` context: app.db.engine
    # is a module-level singleton, and asyncpg connections from its pool
    # can't survive being reused across a fresh event loop per request (the
    # TestClient default outside a `with` block) - DB-backed tests would
    # fail with "another operation is in progress" / "different loop".
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _no_real_celery_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un document uploadé pendant les tests n'est jamais un vrai PDF -
    dispatcher pour de vrai polluerait la queue Redis partagée avec des
    tâches vouées à échouer (et un worker qui tournerait en même temps les
    prendrait). Un test qui veut vérifier le dispatch lui-même
    (test_document_upload_dispatches_text_extraction) réapplique son propre
    monkeypatch par-dessus celui-ci."""
    monkeypatch.setattr("app.routers.dossiers.dispatch_text_extraction", lambda document_id: None)


# Fixtures partagées des tests d'accès aux dossiers (issue #177) : `world` (personnes et groupes), `analyse`.
pytest_plugins = ["tests.access_support", "tests.tool_support"]
