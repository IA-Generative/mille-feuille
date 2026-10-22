"""Les outils d'un agent : qu'est-ce qui peut y figurer. Un outil est un **identifiant** : celui d'un tool interne du
catalogue (`calculatrice`, `base_connaissances`…) ou celui d'un tool d'un serveur MCP (son identifiant en base).

Seuls les outils **ajoutés** sont contrôlés : un outil déjà présent reste accepté même s'il est devenu inaccessible
(serveur supprimé, droit retiré, tool désautorisé), pour qu'on puisse modifier le reste de l'agent. C'est la
personne qui l'édite qui le retire, l'interface le signale."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext
from app.models.analyse import AgentTool
from app.repositories.tool_server_repository import ToolServerRepository
from app.services.tools.ids import unique
from app.services.tools.internal_catalog import get_internal_tool, is_available
from app.services.tools.visibility import can_view_server


@dataclass(frozen=True)
class RefusedTool:
    id: str
    reason: str


class ToolsRefusedError(ValueError):
    """Des outils ne peuvent pas être donnés à l'agent ; `refused` dit lesquels et pourquoi."""

    def __init__(self, refused: Sequence[RefusedTool]) -> None:
        super().__init__(f"{len(refused)} outil(s) refusé(s)")
        self.refused = list(refused)

    @property
    def message(self) -> str:
        return "Ces outils ne peuvent pas être utilisés : " + ", ".join(f"{r.id} ({r.reason})" for r in self.refused)


# Les identifiants de l'ancienne énumération : le contrat de l'API asynchrone (`worker/async_api/contrat.json`) les
# liste, un appelant qui les envoie conformément au contrat ne doit pas être rejeté. Le worker ignore ceux qu'il ne sait
# pas exécuter et le dit dans le journal de l'étape.
LEGACY_IDS = frozenset(tool.value for tool in AgentTool)


def require_internal(tool_ids: Sequence[str]) -> list[str]:
    """Pour les créateurs sans personne derrière (API éphémère) : tools internes seulement. Les identifiants de
    l'ancienne énumération restent acceptés (contrat de l'API) ; tout le reste est refusé."""
    ids = unique(tool_ids)
    refused = [
        RefusedTool(i, "pas encore disponible" if get_internal_tool(i) else "outil inconnu")
        for i in ids
        if not is_available(i) and i not in LEGACY_IDS
    ]
    if refused:
        raise ToolsRefusedError(refused)
    return ids


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def validate_agent_tools(
    db: AsyncSession, user: RequestContext, tool_ids: Sequence[str], *, already: Sequence[str] = ()
) -> list[str]:
    """Renvoie les identifiants sans doublon, ou lève `ToolsRefusedError`. `already` : ceux que l'agent a déjà."""
    ids = unique(tool_ids)
    to_check = [i for i in ids if i not in set(already) and not is_available(i)]
    parsed = {i: _as_uuid(i) for i in to_check}
    found = await ToolServerRepository(db).tools_with_servers([u for u in parsed.values() if u])
    by_id = {str(tool.id): (tool, server) for tool, server in found}

    refused: list[RefusedTool] = []
    for tool_id in to_check:
        match = by_id.get(tool_id)
        if match is None:
            # Un tool interne connu mais pas encore exécutable n'est pas « inconnu » : il reviendra.
            refused.append(
                RefusedTool(tool_id, "pas encore disponible" if get_internal_tool(tool_id) else "outil inconnu")
            )
            continue
        tool, server = match
        visible = can_view_server(user, server)
        if not visible:
            refused.append(RefusedTool(tool_id, "serveur inaccessible"))
        elif not tool.enabled:
            refused.append(RefusedTool(tool_id, "non autorisé par la personne qui a ajouté le serveur"))
    if refused:
        raise ToolsRefusedError(refused)
    return ids
