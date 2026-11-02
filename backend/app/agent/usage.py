"""Consommation de tokens des appels au LLM de l'agent : déclarée en base après chaque appel, sans jamais le faire
échouer. Seuls des compteurs sont gardés (tâche, modèle, tokens), jamais le prompt ni la réponse.

Chaque travail appelle `bind(...)` en début d'exécution pour dire à quoi servent les appels qui suivent ; le contexte
est une contextvar, propre à la tâche asyncio qui l'a posé."""

import contextvars
import logging
import uuid

from app.db import async_session_factory
from app.models.token_usage import TokenUsageKind
from app.schemas.usage import UsageIn
from app.services.usage_service import UsageService

logger = logging.getLogger(__name__)

_context: contextvars.ContextVar[dict | None] = contextvars.ContextVar("agent_usage_context", default=None)


def bind(step: str, *, user_id: str | None = None, dossier_id: str | None = None) -> None:
    """Rattache les appels suivants à un travail, et à la personne / au dossier concernés quand on les connaît."""
    _context.set({"step": step, "user_id": user_id or None, "dossier_id": dossier_id})


async def record(model: str | None, usage, kind: TokenUsageKind = TokenUsageKind.CHAT) -> None:  # noqa: ANN001
    """`usage` est le bloc `usage` d'une réponse OpenAI (ou None)."""
    context = _context.get() or {}
    try:
        entry = UsageIn(
            step=context.get("step") or "unknown",
            model=model or "unknown",
            kind=kind,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            user_id=context.get("user_id"),
            dossier_id=uuid.UUID(context["dossier_id"]) if context.get("dossier_id") else None,
        )
        async with async_session_factory() as db:
            await UsageService(db).record(entry)
    except Exception:
        logger.warning("Impossible de déclarer la consommation de tokens", exc_info=True)
