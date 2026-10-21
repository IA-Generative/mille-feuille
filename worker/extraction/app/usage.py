"""Consommation de tokens : chaque appel au LLM est déclaré au backend (`POST /api/internal/usage`).

Le client OpenAI du worker passe par `http_client()` : un hook lit le bloc `usage` de la réponse, sans toucher aux
appels eux-mêmes. Seuls des **compteurs** partent (tâche, modèle, tokens) : jamais le prompt ni la réponse. Déclarer
la consommation ne doit jamais faire échouer un appel qui a réussi : une erreur est journalisée puis ignorée.

Chaque tâche appelle `bind(...)` en début d'exécution pour dire à quoi servent les appels qui suivent."""

import contextvars
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_context: contextvars.ContextVar[dict | None] = contextvars.ContextVar("usage_context", default=None)
_ENDPOINTS = {"/chat/completions": "chat", "/embeddings": "embedding"}


def bind(step: str, *, user_id: str | None = None, dossier_id: str | None = None) -> None:
    """Rattache les appels suivants à une tâche, et à la personne / au dossier concernés quand on les connaît."""
    _context.set({"step": step, "user_id": user_id or None, "dossier_id": dossier_id})


def _report(response: httpx.Response) -> None:
    kind = next((kind for suffix, kind in _ENDPOINTS.items() if response.request.url.path.endswith(suffix)), None)
    if kind is None or response.status_code >= 400:
        return
    try:
        response.read()
        usage = response.json().get("usage") or {}
        context = _context.get() or {}
        httpx.post(
            f"{settings.BACKEND_INTERNAL_URL}/api/internal/usage",
            headers={"X-App-Token": settings.INTERNAL_WORKER_TOKEN},
            json={
                "step": context.get("step") or "unknown",
                "model": response.json().get("model") or "unknown",
                "kind": kind,
                "input_tokens": usage.get("prompt_tokens") or 0,
                "output_tokens": usage.get("completion_tokens") or 0,
                "user_id": context.get("user_id"),
                "dossier_id": context.get("dossier_id"),
            },
            timeout=5.0,
        ).raise_for_status()
    except Exception:
        logger.warning("Impossible de déclarer la consommation de tokens", exc_info=True)


def http_client() -> httpx.Client:
    return httpx.Client(event_hooks={"response": [_report]}, timeout=httpx.Timeout(600.0, connect=5.0))
