import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import LlmSettings
from app.connectors import redis_connector
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.schemas.llm import ChatCompletionRequest, ChatCompletionResponse
from app.services.usage_service import UsageService

router = APIRouter(prefix="/llm", tags=["Assist"])

# Même clé de cache que app/routers/models.py : quel que soit celui des deux
# qui la peuple en premier sert l'autre gratuitement. Dupliqué plutôt
# qu'importé (comme le client ci-dessous) pour que chaque routeur garde sa
# propre instance patchable indépendamment en test.
_CHAT_MODELS_CACHE_KEY = "llm:chat_models"

_llm_settings = LlmSettings()
_openai_client = (
    AsyncOpenAI(api_key=_llm_settings.OPENAI_API_KEY, base_url=_llm_settings.OPENAI_API_BASE_URL)
    if _llm_settings.is_configured
    else None
)


async def _supports_chat(model_id: str) -> bool:
    try:
        await _openai_client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        return True
    except Exception:
        return False


async def _discover_models(probe: Callable[[str], Awaitable[bool]]) -> list[str]:
    available = await _openai_client.models.list()
    candidate_ids = [model.id for model in available.data]
    supported = await asyncio.gather(*(probe(model_id) for model_id in candidate_ids))
    return sorted(model_id for model_id, ok in zip(candidate_ids, supported, strict=True) if ok)


async def _default_chat_model() -> str | None:
    """Premier modèle chat-capable du hub - utilisé quand l'appelant ne
    précise pas de modèle, pour que l'aide LLM fonctionne sans configuration
    préalable d'un modèle par défaut côté utilisateur."""
    cached = redis_connector.client.get(_CHAT_MODELS_CACHE_KEY)
    if cached is not None:
        model_ids = json.loads(cached)
    else:
        model_ids = await _discover_models(_supports_chat)
        redis_connector.client.set(
            _CHAT_MODELS_CACHE_KEY, json.dumps(model_ids), ex=_llm_settings.CHAT_MODELS_CACHE_TTL_SECONDS
        )
    return model_ids[0] if model_ids else None


@router.post(
    "/complete",
    summary="Chat completion générique utilisée par les boutons d'aide LLM du frontend",
    response_model=ChatCompletionResponse,
)
async def complete(
    body: ChatCompletionRequest,
    user: Annotated[RequestContext, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChatCompletionResponse:
    if _openai_client is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="LLM hub is not configured")

    model = body.model or await _default_chat_model()
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No chat-capable model available on the hub"
        )

    completion = await _openai_client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": body.prompt}]
    )
    usage = completion.usage
    await UsageService(db).record_quietly(
        "llm_assist",
        model,
        usage.prompt_tokens if usage else None,
        usage.completion_tokens if usage else None,
        user.user_id,
    )
    return ChatCompletionResponse(content=completion.choices[0].message.content or "")
