"""Les services du backend dont les outils de l'agent ont besoin, construits hors d'une requête FastAPI (les routeurs
les reçoivent par `Depends`). Ce sont les mêmes constructeurs : les tests les remplacent par des faux ici."""

from app.config import ToolSettings
from app.connectors import redis_connector
from app.services.knowledge.client import HttpKnowledgeClient, KnowledgeClient
from app.services.tools.call_limits import CallLimiter
from app.services.tools.credentials import default_identity_tokens
from app.services.tools.identity_tokens import IdentityTokens
from app.services.tools.mcp_caller import McpToolCaller, ToolCaller


def tool_caller() -> ToolCaller:
    return McpToolCaller()


def identity_tokens() -> IdentityTokens:
    return default_identity_tokens()


def knowledge_client() -> KnowledgeClient:
    return HttpKnowledgeClient()


def call_limiter() -> CallLimiter:
    settings = ToolSettings()
    return CallLimiter(
        redis_connector.client, per_run=settings.TOOL_CALLS_PER_RUN, per_minute=settings.TOOL_CALLS_PER_MINUTE
    )
