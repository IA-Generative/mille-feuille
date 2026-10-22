"""Les outils d'une conversation du chat. Par défaut le modèle choisit parmi les outils que **l'analyse autorise** :
ceux de ses agents, filtrés par les droits de la personne qui discute. Elle peut en **retirer** pour sa conversation,
jamais en ajouter.

Un outil qui **modifie des données** n'est jamais appelé sans l'accord de la personne : le modèle le demande, la demande
reste dans la discussion, la personne décide quand elle veut (voir `services/chat_tool_calls.py`)."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext
from app.models.analyse import Analyse
from app.services.tools.definitions import resolve_tool_definitions
from app.services.tools.ids import unique
from app.services.tools.internal_catalog import available_internal_tools


@dataclass(frozen=True)
class ChatTool:
    id: str
    name: str
    description: str
    kind: str  # "internal" | "mcp"
    server_name: str | None
    side_effect: bool


@dataclass(frozen=True)
class ChatToolsView:
    tools: list[ChatTool] = field(default_factory=list)
    # Les outils que l'analyse prévoit mais que cette personne ne peut pas utiliser (droits, serveur supprimé…).
    unavailable: list[str] = field(default_factory=list)


def analysis_tool_ids(analyse: Analyse) -> list[str]:
    """L'union des outils des agents de l'analyse, sans doublon, dans l'ordre."""
    return unique([tool_id for agent in analyse.agents for tool_id in agent.tools])


async def chat_tools_for(db: AsyncSession, user: RequestContext, analyse: Analyse) -> ChatToolsView:
    """Les outils que l'analyse autorise pour le chat, tels que cette personne peut les utiliser."""
    ids = analysis_tool_ids(analyse)
    internal = {tool.id: tool for tool in available_internal_tools()}
    definitions, unavailable = await resolve_tool_definitions(db, user, [i for i in ids if i not in internal])
    mcp = {definition.id: definition for definition in definitions}
    gone = set(unavailable)

    tools: list[ChatTool] = []
    for tool_id in ids:
        if tool_id in internal:
            tool = internal[tool_id]
            tools.append(ChatTool(tool.id, tool.name, tool.description, "internal", None, tool.side_effect))
        elif tool_id in mcp:
            definition = mcp[tool_id]
            tools.append(
                ChatTool(
                    definition.id,
                    definition.name,
                    definition.description,
                    "mcp",
                    definition.server_name,
                    definition.side_effect,
                )
            )
    # Un identifiant ni interne ni MCP (ancienne énumération…) n'est pas une indisponibilité à signaler : il est ignoré.
    return ChatToolsView(tools=tools, unavailable=[i for i in ids if i in gone and i not in internal])


def tool_ids_for_chat(analyse: Analyse, excluded: Sequence[str]) -> list[str]:
    """Ce que le worker doit donner au modèle : les outils de l'analyse, moins ceux que la personne a retirés."""
    removed = set(excluded)
    return [tool_id for tool_id in analysis_tool_ids(analyse) if tool_id not in removed]
