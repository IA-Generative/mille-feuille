import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import ToolCallLog


class ToolCallLogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(
        self,
        *,
        user_id: str,
        server_id: uuid.UUID | None,
        server_name: str,
        tool_name: str,
        run_id: str | None,
        duration_ms: int,
        outcome: str,
    ) -> ToolCallLog:
        log = ToolCallLog(
            user_id=user_id,
            server_id=server_id,
            server_name=server_name,
            tool_name=tool_name,
            run_id=run_id,
            duration_ms=duration_ms,
            outcome=outcome,
        )
        self.db.add(log)
        await self.db.commit()
        return log
