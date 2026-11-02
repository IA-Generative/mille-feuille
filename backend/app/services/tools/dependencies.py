"""Les dépendances FastAPI des appels d'outils MCP ; les tests les remplacent par des faux."""

from app.config import ToolSettings
from app.connectors import redis_connector
from app.services.tools.call_limits import CallLimiter
from app.services.tools.mcp_caller import McpToolCaller, ToolCaller


def get_tool_caller() -> ToolCaller:
    """Le client réseau des serveurs MCP ; les tests le remplacent par un faux."""
    return McpToolCaller()


def get_call_limiter() -> CallLimiter:
    settings = ToolSettings()
    return CallLimiter(
        redis_connector.client, per_run=settings.TOOL_CALLS_PER_RUN, per_minute=settings.TOOL_CALLS_PER_MINUTE
    )
