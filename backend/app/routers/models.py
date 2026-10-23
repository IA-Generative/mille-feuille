import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from openai import AsyncOpenAI

from app.config import LlmSettings
from app.connectors import redis_connector
from app.core.security.factory import RequestContext, get_current_user
from app.schemas.models import (
    LlmEmbeddingModel,
    LlmEmbeddingModelsResponse,
    LlmModel,
    LlmModelsCacheCleared,
    LlmModelsResponse,
)

router = APIRouter(prefix="/models", tags=["Models"])

_CHAT_MODELS_CACHE_KEY = "llm:chat_models"
_EMBEDDING_MODELS_CACHE_KEY = "llm:embedding_models"

# Module attributes (not closed over) so tests can swap them out with
# monkeypatch.setattr without a live LLM hub or Redis.
_llm_settings = LlmSettings()
_openai_client = (
    AsyncOpenAI(api_key=_llm_settings.OPENAI_API_KEY, base_url=_llm_settings.OPENAI_API_BASE_URL)
    if _llm_settings.is_configured
    else None
)


async def _supports_chat(model_id: str) -> bool:
    """The hub's /models endpoint lists everything it serves (embeddings, TTS,
    vision-only, ...), not just chat models - the only reliable way to tell
    them apart is to actually try a chat completion."""
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


async def _embedding_dimension(model_id: str) -> int | None:
    """La dimension des vecteurs d'un modèle, ou None s'il ne sait pas faire d'embeddings : comme pour le chat, la seule
    façon fiable de le savoir est d'essayer."""
    try:
        response = await _openai_client.embeddings.create(model=model_id, input="ping")
        return len(response.data[0].embedding)
    except Exception:
        return None


async def _discover_embedding_models() -> list[LlmEmbeddingModel]:
    available = await _openai_client.models.list()
    candidate_ids = [model.id for model in available.data]
    dimensions = await asyncio.gather(*(_embedding_dimension(model_id) for model_id in candidate_ids))
    return sorted(
        (
            LlmEmbeddingModel(id=model_id, dimension=dimension)
            for model_id, dimension in zip(candidate_ids, dimensions, strict=True)
            if dimension
        ),
        key=lambda model: model.id,
    )


def _cache_embedding_models(models: list[LlmEmbeddingModel]) -> None:
    redis_connector.client.set(
        _EMBEDDING_MODELS_CACHE_KEY,
        json.dumps([model.model_dump() for model in models]),
        ex=_llm_settings.CHAT_MODELS_CACHE_TTL_SECONDS,
    )


async def embedding_models() -> list[LlmEmbeddingModel]:
    """Les modèles d'embeddings du hub, avec leur dimension (cache Redis, comme les modèles de chat)."""
    if _openai_client is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="LLM hub is not configured")
    cached = redis_connector.client.get(_EMBEDDING_MODELS_CACHE_KEY)
    if cached is not None:
        return [LlmEmbeddingModel(**item) for item in json.loads(cached)]
    models = await _discover_embedding_models()
    _cache_embedding_models(models)
    return models


def _cache_models(model_ids: list[str]) -> None:
    redis_connector.client.set(
        _CHAT_MODELS_CACHE_KEY, json.dumps(model_ids), ex=_llm_settings.CHAT_MODELS_CACHE_TTL_SECONDS
    )


@router.get("", summary="List the LLM hub's models that support chat completions", response_model=LlmModelsResponse)
async def list_models(_: Annotated[RequestContext, Depends(get_current_user)]) -> LlmModelsResponse:
    if _openai_client is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="LLM hub is not configured")

    cached = redis_connector.client.get(_CHAT_MODELS_CACHE_KEY)
    if cached is not None:
        model_ids = json.loads(cached)
    else:
        model_ids = await _discover_models(_supports_chat)
        _cache_models(model_ids)

    return LlmModelsResponse(models=[LlmModel(id=model_id) for model_id in model_ids])


@router.get(
    "/embeddings",
    summary="List the LLM hub's models that produce embeddings, with their vector size",
    response_model=LlmEmbeddingModelsResponse,
)
async def list_embedding_models(_: Annotated[RequestContext, Depends(get_current_user)]) -> LlmEmbeddingModelsResponse:
    return LlmEmbeddingModelsResponse(models=await embedding_models())


@router.post(
    "/embeddings/refresh",
    summary="Force a fresh probe of the LLM hub and refresh the embedding-models cache",
    response_model=LlmEmbeddingModelsResponse,
)
async def refresh_embedding_models(
    _: Annotated[RequestContext, Depends(get_current_user)],
) -> LlmEmbeddingModelsResponse:
    if _openai_client is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="LLM hub is not configured")
    models = await _discover_embedding_models()
    _cache_embedding_models(models)
    return LlmEmbeddingModelsResponse(models=models)


@router.post(
    "/refresh",
    summary="Force a fresh probe of the LLM hub and refresh the chat-models cache",
    response_model=LlmModelsResponse,
)
async def refresh_models(_: Annotated[RequestContext, Depends(get_current_user)]) -> LlmModelsResponse:
    """Ré-interroge le hub (probe OpenAI sur chaque modèle candidat) et
    remplace le contenu du cache Redis. Utile quand de nouveaux modèles ont
    été ajoutés côté hub depuis le dernier remplissage du cache."""
    if _openai_client is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="LLM hub is not configured")

    model_ids = await _discover_models(_supports_chat)
    _cache_models(model_ids)
    return LlmModelsResponse(models=[LlmModel(id=model_id) for model_id in model_ids])


@router.delete(
    "/cache",
    summary="Invalidate the chat-models cache so the next GET /models re-probes the hub",
    response_model=LlmModelsCacheCleared,
)
async def clear_models_cache(_: Annotated[RequestContext, Depends(get_current_user)]) -> LlmModelsCacheCleared:
    redis_connector.client.delete(_CHAT_MODELS_CACHE_KEY)
    return LlmModelsCacheCleared(cleared=True)
