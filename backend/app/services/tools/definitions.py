"""Les définitions des tools MCP qu'un agent peut utiliser, pour que le worker les donne au modèle (nom, description,
schéma des arguments). Le worker n'a pas accès à la base : il demande au backend, au nom de la personne qui a lancé
l'analyse. Un tool que cette personne ne peut pas utiliser (inconnu, serveur invisible, non autorisé) n'est **pas**
renvoyé : l'agent travaille sans, et le dit au modèle plutôt que de le faire échouer."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext
from app.repositories.tool_server_repository import ToolServerRepository
from app.services.tools.ids import unique
from app.services.tools.visibility import can_view_server


@dataclass(frozen=True)
class ToolDefinition:
    id: str
    name: str
    description: str
    server_name: str
    side_effect: bool
    input_schema: dict[str, Any] = field(default_factory=dict)


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def resolve_tool_definitions(
    db: AsyncSession, user: RequestContext, tool_ids: Sequence[str]
) -> tuple[list[ToolDefinition], list[str]]:
    """Renvoie les définitions utilisables (dans l'ordre demandé) et les identifiants qui ne le sont pas."""
    ids = unique(tool_ids)
    parsed = {tool_id: _as_uuid(tool_id) for tool_id in ids}
    found = await ToolServerRepository(db).tools_with_servers([u for u in parsed.values() if u])
    by_id = {str(tool.id): (tool, server) for tool, server in found}

    usable: list[ToolDefinition] = []
    unavailable: list[str] = []
    for tool_id in ids:
        match = by_id.get(tool_id)
        if match is None or not match[0].enabled or not can_view_server(user, match[1]):
            unavailable.append(tool_id)
            continue
        tool, server = match
        usable.append(
            ToolDefinition(
                id=tool_id,
                name=tool.name,
                description=tool.description,
                server_name=server.name,
                side_effect=tool.side_effect,
                input_schema=tool.input_schema,
            )
        )
    return usable, unavailable
