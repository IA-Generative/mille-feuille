import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_tool_call import ChatToolCall, ChatToolCallStatus

SUPERSEDED_RESULT = "La personne a écrit un autre message sans répondre : l'appel n'a pas été fait."
REFUSED_RESULT = "La personne a refusé cet appel : il n'a pas été fait."


class ChatToolCallRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add_batch(
        self, *, conversation_id: uuid.UUID, message_id: uuid.UUID, calls: Sequence[dict]
    ) -> list[ChatToolCall]:
        rows = [
            ChatToolCall(
                conversation_id=conversation_id,
                message_id=message_id,
                position=position,
                llm_call_id=call["llm_call_id"],
                function_name=call["function_name"],
                tool_id=call["tool_id"],
                tool_name=call.get("tool_name", ""),
                server_name=call.get("server_name", ""),
                arguments=call.get("arguments", {}),
                side_effect=call.get("side_effect", False),
                status=ChatToolCallStatus(call["status"]),
                result=call.get("result"),
            )
            for position, call in enumerate(calls)
        ]
        self.db.add_all(rows)
        await self.db.commit()
        return rows

    async def get(self, call_id: uuid.UUID) -> ChatToolCall | None:
        return await self.db.get(ChatToolCall, call_id)

    async def for_ids(self, conversation_id: uuid.UUID, ids: Sequence[uuid.UUID]) -> list[ChatToolCall]:
        result = await self.db.execute(
            select(ChatToolCall).where(ChatToolCall.conversation_id == conversation_id, ChatToolCall.id.in_(ids))
        )
        return list(result.scalars())

    async def pending_of_message(self, message_id: uuid.UUID) -> list[ChatToolCall]:
        result = await self.db.execute(
            select(ChatToolCall)
            .where(ChatToolCall.message_id == message_id, ChatToolCall.status == ChatToolCallStatus.PENDING)
            .order_by(ChatToolCall.position)
        )
        return list(result.scalars())

    async def supersede_pending(self, conversation_id: uuid.UUID) -> int:
        """La personne écrit un autre message avant de décider : les demandes en attente n'auront pas de suite."""
        result = await self.db.execute(
            select(ChatToolCall).where(
                ChatToolCall.conversation_id == conversation_id, ChatToolCall.status == ChatToolCallStatus.PENDING
            )
        )
        calls = list(result.scalars())
        for call in calls:
            call.status = ChatToolCallStatus.SUPERSEDED
            call.result = SUPERSEDED_RESULT
        await self.db.commit()
        return len(calls)

    async def decide(self, call: ChatToolCall, *, allow: bool, user_id: str, comment: str | None = None) -> None:
        """Un refus porte le texte de la personne s'il y en a un : le modèle le lit comme résultat de l'appel."""
        call.status = ChatToolCallStatus.APPROVED if allow else ChatToolCallStatus.REFUSED
        call.result = (
            None if allow else (f"{REFUSED_RESULT} Elle précise : « {comment} »" if comment else REFUSED_RESULT)
        )
        call.decided_by = user_id
        call.decided_at = datetime.now(UTC)

    async def record_result(self, call: ChatToolCall, result: str) -> None:
        call.status = ChatToolCallStatus.EXECUTED
        call.result = result
        await self.db.commit()
