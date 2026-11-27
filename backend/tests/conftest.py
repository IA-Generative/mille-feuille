import asyncio
import base64
import os

import pytest
from fastapi.testclient import TestClient

from app.core.security.factory import RequestContext
from app.main import app
from app.services.permissions import Permission

# Clés de chiffrement des tests, construites ici : aucune clé écrite dans le dépôt. Lues à la première utilisation.
os.environ.setdefault("ENCRYPTION_KEYS", f"test:{base64.b64encode(bytes(32)).decode()}")
os.environ.setdefault("EMAIL_INDEX_KEY", base64.b64encode(bytes(range(32))).decode())


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
    # Supprimer un dossier déposerait la suppression de son index de recherche sur la file partagée.
    monkeypatch.setattr("app.repositories.dossier_repository.dispatch_drop_index", lambda dossier_id: None)


@pytest.fixture(autouse=True)
def _drain_agent_jobs(request: pytest.FixtureRequest):
    """Un travail lancé en arrière-plan (envoi d'un message de chat...) ne doit pas survivre à son test : il
    tournerait pendant le suivant et y appellerait son faux LLM (`KeyError: 'Hello stats'`, ou une question en trop dans
    les appels comptés). On l'annule et on l'attend avant de passer au test suivant. Sans effet pour un test qui
    n'utilise pas `client` (pas d'application, donc pas de travail)."""
    # Pris avant le test : à la fin, la fixture serait peut-être déjà démontée. Seul le `client` de cette suite compte
    # (certains fichiers de tests définissent le leur, sans application).
    client = request.getfixturevalue("client") if "client" in request.fixturenames else None
    yield
    if not isinstance(client, TestClient):
        return
    from app.agent.runner import agent_runner

    async def drain() -> None:
        running = list(agent_runner._tasks.values())
        for task in running:
            task.cancel()
        if running:
            await asyncio.gather(*running, return_exceptions=True)

    client.portal.call(drain)


# Fixtures partagées des tests d'accès aux dossiers (issue #177) : `world` (personnes et groupes), `analyse`.
pytest_plugins = ["tests.access_support", "tests.tool_support"]


@pytest.fixture(autouse=True)
def open_analyses(monkeypatch: pytest.MonkeyPatch) -> None:
    """La plupart des tests portent sur autre chose que les droits : pour eux, chaque identité voit toutes les
    analyses, peut en créer et a toutes les permissions. Les vraies règles (#662, #664) se testent dans
    test_analyse_access.py et test_role_permissions.py, qui neutralisent ce préalable en redéfinissant cette
    fixture."""
    from sqlalchemy import true

    for module in ("app.services.analyse_access", "app.services.dossier_access"):
        monkeypatch.setattr(f"{module}.membership_clause", lambda *args, **kwargs: true())

    async def any_group(db, user, permission) -> list[str]:
        return list(user.groups) or ["/dev-tests"]

    monkeypatch.setattr("app.services.analyse_creation.groups_allowing", any_group)

    # Les rôles (#664) : de même, chaque identité peut tout sur ce qu'elle voit.
    async def everything(*args, **kwargs):
        return set(Permission)

    for name in ("group_permissions", "analyse_permissions", "dossier_permissions"):
        monkeypatch.setattr(f"app.services.role_permissions.{name}", everything)

    async def everything_for_each(db, dossiers, user):
        return {dossier.id: set(Permission) for dossier in dossiers}

    monkeypatch.setattr("app.services.role_permissions.permissions_by_dossier", everything_for_each)


@pytest.fixture
def without_role(monkeypatch: pytest.MonkeyPatch):
    """Retire tout rôle aux personnes désignées, les autres gardant tout : pour vérifier qu'une route refuse."""

    def apply(*user_ids: str) -> None:
        async def granted(*args, **kwargs):
            user = next(argument for argument in args if isinstance(argument, RequestContext))
            return set() if user.user_id in user_ids else set(Permission)

        for name in ("group_permissions", "analyse_permissions", "dossier_permissions"):
            monkeypatch.setattr(f"app.services.role_permissions.{name}", granted)

    return apply
