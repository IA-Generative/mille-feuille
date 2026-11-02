"""Ce que le chat montre pendant qu'il travaille : les étapes (en base, relues par le flux SSE et à la reconnexion)
et les morceaux de la réponse (dans le flux Redis, voir services/chat_stream.py)."""

import json
import logging
import time
import uuid
from typing import Any

from app.db import async_session_factory
from app.models.chat_event import ChatEventKind
from app.repositories.dossier_repository import DossierRepository
from app.schemas.message_execution import MAX_ARGUMENTS_CHARS, MAX_NOTES, MAX_RESULT_CHARS, MAX_STEPS
from app.services import chat_stream

logger = logging.getLogger(__name__)

# Les morceaux sont regroupés : ni un message par jeton, ni une réponse qui n'arrive qu'à la fin.
FLUSH_EVERY_SECONDS = 0.06
FLUSH_EVERY_CHARS = 24


def _clipped(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + " […]"


def _arguments(arguments: Any) -> dict:
    """Les arguments d'un appel, bornés : un tableau énorme ne doit pas alourdir le message."""
    if not isinstance(arguments, dict):
        return {}
    try:
        text = json.dumps(arguments, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return {}
    return arguments if len(text) <= MAX_ARGUMENTS_CHARS else {"…": _clipped(text, MAX_ARGUMENTS_CHARS)}


class ChatEvents:
    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self._buffer = ""
        self._last_flush = time.monotonic()
        # Le détail de l'exécution, gardé avec le message (voir `execution`) : les appels d'outils avec leurs
        # arguments et leurs résultats entiers (le flux vers le navigateur n'en porte que le début), les écarts du
        # cas normal, et ce que le plan a décidé.
        self._started = time.monotonic()
        self._steps: list[dict[str, Any]] = []
        self._omitted = 0
        self._notes: list[str] = []
        self.meta: dict[str, Any] = {}

    def _elapsed_ms(self) -> int:
        return int((time.monotonic() - self._started) * 1000)

    def note(self, text: str) -> None:
        """Un écart du cas normal (appel d'outil repris, réponse redemandée, limite d'appels atteinte)."""
        if text not in self._notes and len(self._notes) < MAX_NOTES:
            self._notes.append(text)

    def _trace(self, kind: str, data: dict, full: str | None) -> None:
        if kind == "tool_call":
            if len(self._steps) >= MAX_STEPS:
                self._omitted += 1
                return
            self._steps.append(
                {
                    "tool_name": str(data.get("tool_name", "")),
                    "agent": data.get("agent"),
                    "arguments": _arguments(data.get("arguments")),
                    "result": None,
                    "at_ms": self._elapsed_ms(),
                    "duration_ms": None,
                }
            )
        elif kind == "tool_result":
            # Le résultat va avec le dernier appel de cet outil qui n'en a pas encore.
            step = next(
                (
                    step
                    for step in reversed(self._steps)
                    if step["tool_name"] == data.get("tool_name") and step["result"] is None
                ),
                None,
            )
            if step is not None:
                text = full if full is not None else str(data.get("preview", ""))
                step["result"] = _clipped(text, MAX_RESULT_CHARS)
                step["duration_ms"] = self._elapsed_ms() - step["at_ms"]

    def execution(self) -> dict[str, Any]:
        """Le détail de l'exécution à déposer avec le message (voir `schemas/message_execution.py`)."""
        return {
            **self.meta,
            "duration_ms": self._elapsed_ms(),
            "notes": list(self._notes),
            "steps": list(self._steps),
            "omitted_steps": self._omitted,
        }

    async def emit(self, kind: str, data: dict) -> None:
        """Une étape (tool_call, tool_result, thinking, done, error), déposée en base ; jamais bloquante. `data` peut
        porter `full` (le résultat entier d'un outil) : gardé pour le détail de l'exécution, jamais envoyé au
        navigateur."""
        data = dict(data)
        full = data.pop("full", None)
        self._trace(kind, data, full)
        if kind == "note":  # un écart du cas normal : pour le détail seulement, pas une étape à montrer
            self.note(str(data.get("text", "")))
            return
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
