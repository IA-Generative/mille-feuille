import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext
from app.models.tool import Tool, ToolAuthMode, ToolServer, ToolVisibility
from app.services.tools.mcp_discovery import DiscoveredTool
from app.services.tools.visibility import visible_clause


def _to_tool(discovered: DiscoveredTool, *, enabled: bool) -> Tool:
    return Tool(
        name=discovered.name,
        description=discovered.description,
        input_schema=discovered.input_schema,
        side_effect=discovered.side_effect,
        enabled=enabled,
    )


def _owner_name(owner: RequestContext) -> str:
    return " ".join(part for part in (owner.first_name, owner.last_name) if part) or owner.email


class ToolServerRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        name: str,
        url: str,
        auth_mode: ToolAuthMode,
        visibility: ToolVisibility,
        audience: str | None,
        owner: RequestContext,
        tools: Sequence[DiscoveredTool],
        enabled_names: Sequence[str],
    ) -> ToolServer:
        server = ToolServer(
            name=name.strip(),
            url=url,
            auth_mode=auth_mode,
            visibility=visibility,
            audience=audience,
            created_by=owner.user_id,
            owner_name=_owner_name(owner),
            groups=list(owner.groups),
            tools=[_to_tool(tool, enabled=tool.name in enabled_names) for tool in tools],
        )
        self.db.add(server)
        await self.db.commit()
        await self.db.refresh(server)
        return server

    async def get(self, server_id: uuid.UUID) -> ToolServer | None:
        result = await self.db.execute(select(ToolServer).where(ToolServer.id == server_id))
        return result.scalar_one_or_none()

    async def tools_with_servers(self, tool_ids: Sequence[uuid.UUID]) -> Sequence[tuple[Tool, ToolServer]]:
        """Les tools MCP demandés, chacun avec son serveur (pour vérifier les droits sans chargement paresseux)."""
        if not tool_ids:
            return []
        result = await self.db.execute(
            select(Tool, ToolServer).join(ToolServer, Tool.server_id == ToolServer.id).where(Tool.id.in_(tool_ids))
        )
        return [(tool, server) for tool, server in result.all()]

    async def list_visible(
        self, user: RequestContext, *, query: str | None, page: int, page_size: int
    ) -> tuple[Sequence[ToolServer], int]:
        conditions = [visible_clause(user.user_id, user.is_admin, user.groups)]
        if query:
            like = f"%{query.strip()}%"
            conditions.append(or_(ToolServer.name.ilike(like), ToolServer.url.ilike(like)))
        total = await self.db.scalar(select(func.count()).select_from(ToolServer).where(*conditions))
        result = await self.db.execute(
            select(ToolServer)
            .where(*conditions)
            .order_by(ToolServer.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return result.scalars().all(), total or 0

    async def refresh_tools(self, server: ToolServer, discovered: Sequence[DiscoveredTool]) -> ToolServer:
        """Aligne les tools sur ce que le serveur expose : les existants sont mis à jour en gardant leur autorisation,
        les nouveaux arrivent **non autorisés** (la personne ne les a pas choisis), les disparus sont retirés."""
        by_name = {tool.name: tool for tool in discovered}
        for tool in list(server.tools):
            found = by_name.pop(tool.name, None)
            if found is None:
                server.tools.remove(tool)
                continue
            tool.description, tool.input_schema, tool.side_effect = (
                found.description,
                found.input_schema,
                found.side_effect,
            )
        server.tools.extend(_to_tool(tool, enabled=False) for tool in by_name.values())
        server.synced_at = func.now()
        await self.db.commit()
        await self.db.refresh(server)
        return server

    async def delete(self, server: ToolServer) -> None:
        await self.db.delete(server)
        await self.db.commit()
