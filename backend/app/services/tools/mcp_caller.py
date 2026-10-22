"""L'appel d'un tool d'un serveur MCP (`tools/call`). Le client réseau est isolé derrière `ToolCaller` : le service en
dépend, les tests le remplacent par un faux."""

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


@dataclass(frozen=True)
class RawToolResult:
    text: str
    is_error: bool


class CallTimeoutError(Exception):
    """Le serveur n'a pas répondu dans le délai."""


class CallFailedError(Exception):
    """Le serveur ne répond pas, ou pas comme un serveur MCP."""


class ToolCaller(Protocol):
    async def call_tool(
        self, url: str, headers: dict[str, str], name: str, arguments: dict[str, Any], timeout: float
    ) -> RawToolResult: ...


def result_text(content: list[Any]) -> str:
    """Le texte d'une réponse MCP ; un bloc qui n'est pas du texte est signalé, jamais transmis tel quel."""
    parts = [
        block.text if getattr(block, "type", "") == "text" else f"[contenu {block.type} non transmis]"
        for block in content
    ]
    return "\n".join(parts)


class McpToolCaller:
    """Client réel : Streamable HTTP. `transport` sert aux tests (appel en mémoire)."""

    def __init__(self, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def call_tool(
        self, url: str, headers: dict[str, str], name: str, arguments: dict[str, Any], timeout: float
    ) -> RawToolResult:
        try:
            async with asyncio.timeout(timeout):
                async with httpx2.AsyncClient(headers=headers, timeout=timeout, transport=self._transport) as http:
                    async with streamable_http_client(url, http_client=http) as (read, write):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            result = await session.call_tool(name, arguments)
        except TimeoutError as error:
            raise CallTimeoutError from error
        except Exception as error:  # le SDK lève des erreurs de transport variées : une seule réponse
            raise CallFailedError from error
        return RawToolResult(text=result_text(result.content), is_error=bool(result.is_error))
