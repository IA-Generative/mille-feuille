"""Ce que le chat montre pendant qu'il travaille : les étapes (en base, relues par le flux SSE et à la reconnexion)
et les morceaux de la réponse (dans le flux Redis, voir services/chat_stream.py)."""

import logging
import time
import uuid

from app.db import async_session_factory
from app.models.chat_event import ChatEventKind
from app.repositories.dossier_repository import DossierRepository
from app.services import chat_stream

logger = logging.getLogger(__name__)

# Les morceaux sont regroupés : ni un message par jeton, ni une réponse qui n'arrive qu'à la fin.
FLUSH_EVERY_SECONDS = 0.06
FLUSH_EVERY_CHARS = 24


class ChatEvents:
    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self._buffer = ""
        self._last_flush = time.monotonic()

    async def emit(self, kind: str, data: dict) -> None:
        """Une étape (tool_call, tool_result, thinking, done, error), déposée en base ; jamais bloquante."""
        try:
            async with async_session_factory() as db:
                await DossierRepository(db).add_chat_event(uuid.UUID(self.conversation_id), ChatEventKind(kind), data)
        except Exception:
            logger.warning("Événement %s non déposé (conversation %s)", kind, self.conversation_id, exc_info=True)

    async def start(self) -> None:
        await chat_stream.reset(self.conversation_id)

    async def delta(self, text: str) -> None:
        self._buffer += text
        if len(self._buffer) >= FLUSH_EVERY_CHARS or time.monotonic() - self._last_flush >= FLUSH_EVERY_SECONDS:
            await self.flush()

    async def flush(self) -> None:
        if self._buffer:
            text, self._buffer = self._buffer, ""
            await chat_stream.publish(self.conversation_id, text)
        self._last_flush = time.monotonic()
