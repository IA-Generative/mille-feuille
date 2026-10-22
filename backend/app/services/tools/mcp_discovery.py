"""Découverte des tools d'un serveur MCP (`tools/list`). Le client réseau est isolé derrière `ToolLister` : les routes
en dépendent, les tests le remplacent par un faux."""

from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp_types import PaginatedRequestParams


@dataclass(frozen=True)
class DiscoveredTool:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    # Déduit de l'annotation `readOnlyHint` ; sans elle, on suppose que le tool modifie des données.
    side_effect: bool = True


class DiscoveryError(Exception):
    """Le serveur ne répond pas, ou pas comme un serveur MCP ; le message est affichable."""


class ToolLister(Protocol):
    async def list_tools(self, url: str, headers: dict[str, str], timeout: float) -> list[DiscoveredTool]: ...


def to_discovered_tool(tool: Any) -> DiscoveredTool:
    read_only = bool(getattr(getattr(tool, "annotations", None), "read_only_hint", False))
    return DiscoveredTool(
        name=tool.name,
        description=tool.description or "",
        input_schema=tool.input_schema or {},
        side_effect=not read_only,
    )


class McpToolLister:
    """Client réel : Streamable HTTP, avec pagination par curseur. `transport` sert aux tests (appel en mémoire)."""

    def __init__(self, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def list_tools(self, url: str, headers: dict[str, str], timeout: float) -> list[DiscoveredTool]:
        try:
            async with httpx2.AsyncClient(headers=headers, timeout=timeout, transport=self._transport) as http_client:
                async with streamable_http_client(url, http_client=http_client) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools: list[DiscoveredTool] = []
                        cursor: str | None = None
                        while True:
                            page = await session.list_tools(
                                params=PaginatedRequestParams(cursor=cursor) if cursor else None
                            )
                            tools.extend(to_discovered_tool(tool) for tool in page.tools)
                            cursor = page.next_cursor
                            if not cursor:
                                return tools
        except Exception as error:  # le SDK lève des erreurs de transport variées : une seule réponse pour la personne
            raise DiscoveryError("Le serveur ne répond pas comme un serveur MCP.") from error
