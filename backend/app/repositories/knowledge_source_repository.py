import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext
from app.models.knowledge_source import KnowledgeSource
from app.models.tool import ToolAuthMode, ToolVisibility
from app.services.tools.visibility import visible_clause


def _owner_name(owner: RequestContext) -> str:
    return " ".join(part for part in (owner.first_name, owner.last_name) if part) or owner.email


class KnowledgeSourceRepository:
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
    ) -> KnowledgeSource:
        source = KnowledgeSource(
            name=name,
            url=url,
            auth_mode=auth_mode,
            visibility=visibility,
            audience=audience,
            created_by=owner.user_id,
            owner_name=_owner_name(owner),
            groups=list(owner.groups),
        )
        self.db.add(source)
        await self.db.commit()
        await self.db.refresh(source)
        return source

    async def get(self, source_id: uuid.UUID) -> KnowledgeSource | None:
        result = await self.db.execute(select(KnowledgeSource).where(KnowledgeSource.id == source_id))
        return result.scalar_one_or_none()

    async def list_visible(
        self, user: RequestContext, *, query: str | None, page: int, page_size: int
    ) -> tuple[Sequence[KnowledgeSource], int]:
        conditions = [visible_clause(user.user_id, user.is_admin, user.groups, KnowledgeSource)]
        if query:
            like = f"%{query.strip()}%"
            conditions.append(or_(KnowledgeSource.name.ilike(like), KnowledgeSource.url.ilike(like)))
        total = await self.db.scalar(select(func.count()).select_from(KnowledgeSource).where(*conditions))
        result = await self.db.execute(
            select(KnowledgeSource)
            .where(*conditions)
            .order_by(KnowledgeSource.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return result.scalars().all(), total or 0

    async def delete(self, source: KnowledgeSource) -> None:
        await self.db.delete(source)
        await self.db.commit()
