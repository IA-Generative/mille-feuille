from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.transport_security import TransportSecuritySettings

from app.config import KeycloakSettings
from app.logging_config import configure_logging
from app.mcp.auth import BearerTokenAuthMiddleware
from app.mcp.helper_server import mcp_server as helper_mcp_server
from app.mcp.server import mcp_server
from app.routers.admin_document_templates import router as admin_document_templates_router
from app.routers.admin_generation_prompt import router as admin_generation_prompt_router
from app.routers.admin_reports import router as admin_reports_router
from app.routers.admin_stats import router as admin_stats_router
from app.routers.admin_tasks import router as admin_tasks_router
from app.routers.agent_conversations import router as agent_conversations_router
from app.routers.analyses import public_router as analyses_public_router
from app.routers.analyses import router as analyses_router
from app.routers.analysis_collaboration import router as analysis_collaboration_router
from app.routers.analysis_proposals import router as analysis_proposals_router
from app.routers.app_tokens import router as app_tokens_router
from app.routers.assist import router as assist_router
from app.routers.auth import router as auth_router
from app.routers.cgu import admin_router as cgu_admin_router
from app.routers.cgu import public_router as cgu_public_router
from app.routers.conversations import router as conversations_router
from app.routers.dashboard import router as dashboard_router
from app.routers.document_drafts import router as document_drafts_router
from app.routers.dossier_analyses import router as dossier_analyses_router
from app.routers.dossier_events import router as dossier_events_router
from app.routers.dossier_notes import router as dossier_notes_router
from app.routers.dossiers import router as dossiers_router
from app.routers.ephemeral import router as ephemeral_router
from app.routers.generated_documents import router as generated_documents_router
from app.routers.health import router as health_router
from app.routers.internal import router as internal_router
from app.routers.internal_agent import agent_conversations_router as internal_agent_conversations_router
from app.routers.internal_agent import router as internal_agent_router
from app.routers.models import router as models_router
from app.routers.notifications import router as notifications_router
from app.routers.profile import router as profile_router
from app.routers.reports import router as reports_router
from app.routers.sources import router as sources_router
from app.routers.tool_servers import router as tool_servers_router
from app.routers.tools import router as tools_router
from app.routers.tracking import router as tracking_router
from app.routers.usage import internal_router as internal_usage_router
from app.routers.usage import router as usage_router
from app.routers.user_tasks import router as user_tasks_router
from app.routers.users import router as users_router
from app.routers.work_slots import router as work_slots_router

# Uvicorn configure son logging avant d'importer l'app : on le remplace ici par du JSON (access log inclus).
configure_logging()

_keycloak_settings = KeycloakSettings()

# Streamable HTTP monté sous /mcp (voir mcp/README.md). L'app Starlette
# renvoyée par streamable_http_app() porte son propre lifespan
# (session_manager.run()) : Starlette ne le déclenche jamais tout seul pour
# une sous-app montée via app.mount(), il faut l'entrer explicitement dans
# le lifespan du process qui l'héberge - ici celui du backend.
# streamable_http_path="/" : la route interne est à la racine de cette
# sous-app, montée elle-même sous /mcp juste en dessous - sans ça, l'URL
# finale serait /mcp/mcp (préfixe en double).
#
# transport_security : la protection anti DNS-rebinding du SDK MCP (activée
# par défaut dès que host="127.0.0.1"/"localhost") valide le header Host
# contre une liste fixe - inadaptée ici, ce endpoint est servi derrière le
# même reverse proxy/domaine que le reste de l'API (BACKEND_PUBLIC_URL,
# configurable par déploiement) et protégé par le même Bearer token que
# n'importe quelle route /api/*, pas par du same-origin. Désactivée plutôt
# que maintenue en synchronisation avec BACKEND_PUBLIC_URL.
mcp_app = mcp_server.streamable_http_app(
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
# Serveur MCP helper (issue #50, docs/mcp-helper-agent-plan.md) : mêmes
# raisons de config que mcp_app ci-dessus, monté séparément sous /mcp/helper
# - deux cycles de vie différents (one-shot éphémère vs persistant/
# interactif), voir le plan pour le détail.
helper_mcp_app = helper_mcp_server.streamable_http_app(
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _app_version() -> str:
    """Version du paquet (`project.version` de pyproject.toml, tenue à jour par release-please), affichée par Swagger
    et dans openapi.json. « inconnue » si le paquet n'est pas installé (exécution depuis les sources, sans uv sync)."""
    try:
        return version("mille-feuille-backend")
    except PackageNotFoundError:
        return "inconnue"


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp_app.router.lifespan_context(mcp_app), helper_mcp_app.router.lifespan_context(helper_mcp_app):
        yield


app = FastAPI(
    title="mille-feuille BFF",
    version=_app_version(),
    docs_url="/api/docs",
    redoc_url="/api/redocs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Auth", "description": "Login/logout via Keycloak, session management."},
        {"name": "Health", "description": "Liveness/readiness of the API and its dependencies."},
        {"name": "Analyses", "description": "Classification, extraction et agents d'une analyse."},
        {"name": "Dossiers", "description": "Dossiers usagers liés à une analyse, et suivi de leur exécution."},
        {"name": "Conversations", "description": "Conversations de l'utilisateur courant, tous dossiers confondus."},
        {"name": "Models", "description": "Modèles LLM disponibles sur le hub configuré, pour peupler un sélecteur."},
        {"name": "Assist", "description": "Chat completion générique utilisée par les boutons d'aide LLM du frontend."},
        {"name": "Internal", "description": "Callbacks des workers Celery (jeton partagé, pas d'auth Keycloak)."},
        {"name": "App tokens", "description": "Jetons permettant à une application externe d'appeler l'API."},
        {"name": "Reports", "description": "Signalements libres (bug/idée/question) envoyés par les utilisateurs."},
        {"name": "CGU", "description": "Conditions générales d'utilisation versionnées."},
        {"name": "Profile", "description": "Préférences et statistiques de l'utilisateur courant."},
        {"name": "Admin", "description": "Vues et actions réservées aux administrateurs."},
        {
            "name": "Ephemeral",
            "description": "Analyses et dossiers à la demande, temporaires par défaut (TTL) - "
            "voir docs/ephemeral-api.md.",
        },
        {
            "name": "Agent",
            "description": "Conversation avec l'agent helper (recherche/création d'analyses et de dossiers, "
            "lancement du pipeline) - pas rattachée à un dossier unique, voir docs/mcp-helper-agent-plan.md.",
        },
    ],
)

# Explicit origin (not "*") required: credentialed cookie requests are
# rejected by browsers if allow_origins is a wildcard.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_keycloak_settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth")
app.include_router(health_router, prefix="/api")
app.include_router(analyses_public_router, prefix="/api")
app.include_router(analyses_router, prefix="/api")
app.include_router(agent_conversations_router, prefix="/api")
app.include_router(dossiers_router, prefix="/api")
app.include_router(sources_router, prefix="/api")
app.include_router(dossier_analyses_router, prefix="/api")
app.include_router(analysis_collaboration_router, prefix="/api")
app.include_router(dossier_events_router, prefix="/api")
app.include_router(dossier_notes_router, prefix="/api")
app.include_router(document_drafts_router, prefix="/api")
app.include_router(generated_documents_router, prefix="/api")
app.include_router(analysis_proposals_router, prefix="/api")
app.include_router(conversations_router, prefix="/api")
app.include_router(models_router, prefix="/api")
app.include_router(assist_router, prefix="/api")
app.include_router(internal_router, prefix="/api")
app.include_router(internal_agent_router, prefix="/api")
app.include_router(internal_agent_conversations_router, prefix="/api")
app.include_router(app_tokens_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(admin_reports_router, prefix="/api")
app.include_router(admin_stats_router, prefix="/api")
app.include_router(admin_tasks_router, prefix="/api")
app.include_router(cgu_public_router, prefix="/api")
app.include_router(cgu_admin_router, prefix="/api")
app.include_router(admin_document_templates_router, prefix="/api")
app.include_router(admin_generation_prompt_router, prefix="/api")
app.include_router(profile_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(tracking_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(work_slots_router, prefix="/api")
app.include_router(user_tasks_router, prefix="/api")
app.include_router(ephemeral_router, prefix="/api")
app.include_router(tool_servers_router, prefix="/api")
app.include_router(tools_router, prefix="/api")
app.include_router(usage_router, prefix="/api")
app.include_router(internal_usage_router, prefix="/api")
# /mcp/helper doit être monté avant /mcp : Starlette résout les Mount par
# préfixe dans l'ordre d'enregistrement, et "/mcp/helper/..." commence
# aussi par "/mcp" - sans cet ordre, tout irait au mauvais sous-app.
app.mount("/mcp/helper", BearerTokenAuthMiddleware(helper_mcp_app))
app.mount("/mcp", BearerTokenAuthMiddleware(mcp_app))
