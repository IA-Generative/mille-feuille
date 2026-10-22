"""Découverte des tools d'un serveur MCP : garde d'URL, en-têtes d'authentification, puis `tools/list`. C'est le seul
chemin qui parle à un serveur MCP ajouté par une personne ; les routes n'enchaînent pas ces étapes elles-mêmes."""

from app.config import ToolSettings
from app.models.tool import ToolAuthMode
from app.services.tools.credentials import headers_for
from app.services.tools.identity_tokens import IdentityTokens
from app.services.tools.mcp_discovery import DiscoveredTool, ToolLister
from app.services.tools.url_guard import ensure_safe_url


async def discover_tools(
    url: str,
    auth_mode: ToolAuthMode,
    *,
    acting_user: str | None,
    lister: ToolLister,
    audience: str | None = None,
    identity_tokens: IdentityTokens | None = None,
) -> tuple[str, list[DiscoveredTool]]:
    """Renvoie l'URL vérifiée et les tools du serveur. Lève `UnsafeUrlError`, `CredentialsUnavailableError` ou
    `DiscoveryError` : la route les traduit en réponses."""
    settings = ToolSettings()
    safe_url = await ensure_safe_url(url, settings)
    headers = await headers_for(auth_mode, acting_user=acting_user, audience=audience, identity_tokens=identity_tokens)
    tools = await lister.list_tools(safe_url, headers, settings.TOOL_DISCOVERY_TIMEOUT_SECONDS)
    return safe_url, tools
