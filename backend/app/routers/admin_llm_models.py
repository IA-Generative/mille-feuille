"""Routes d'administration des modèles LLM : leurs capacités (définies par l'administrateur), les modèles enregistrés
avec ce qu'ils savent faire, leur ordre, et le réglage « un seul modèle / auto ». Réservées aux administrateurs.

Le premier modèle actif fait tout par défaut ; en mode auto, les capacités que la demande demande décident."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import model_router
from app.core.security.admin import require_admin
from app.db import get_db
from app.schemas.llm_model import (
    LlmCapabilityIn,
    LlmCapabilityOut,
    LlmCapabilityUpdate,
    LlmHubModelsOut,
    LlmModelCreate,
    LlmModelOrder,
    LlmModelOut,
    LlmModelUpdate,
    LlmRoutingOut,
)
from app.services import llm_hub, llm_models

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Introuvable")
_DUPLICATE = HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce nom existe déjà")


# --- Capacités ---


@router.get("/llm-capabilities", response_model=list[LlmCapabilityOut])
async def list_capabilities(db: Annotated[AsyncSession, Depends(get_db)]):
    return await llm_models.list_capabilities(db)


@router.post("/llm-capabilities", response_model=LlmCapabilityOut, status_code=status.HTTP_201_CREATED)
async def add_capability(body: LlmCapabilityIn, db: Annotated[AsyncSession, Depends(get_db)]):
    try:
        capability = await llm_models.create_capability(db, name=body.name, description=body.description)
    except llm_models.DuplicateError:
        raise _DUPLICATE from None
    model_router.forget()
    return capability


@router.patch("/llm-capabilities/{capability_id}", response_model=LlmCapabilityOut)
async def update_capability(
    capability_id: uuid.UUID, body: LlmCapabilityUpdate, db: Annotated[AsyncSession, Depends(get_db)]
):
    try:
        capability = await llm_models.update_capability(db, capability_id, body.model_dump(exclude_none=True))
    except llm_models.NotFoundError:
        raise _NOT_FOUND from None
    except llm_models.DuplicateError:
        raise _DUPLICATE from None
    model_router.forget()
    return capability


@router.delete("/llm-capabilities/{capability_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_capability(capability_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    """Supprime la capacité : elle est retirée de tous les modèles."""
    try:
        await llm_models.delete_capability(db, capability_id)
    except llm_models.NotFoundError:
        raise _NOT_FOUND from None
    model_router.forget()


# --- Modèles ---


@router.get("/llm-models", response_model=list[LlmModelOut])
async def list_llm_models(db: Annotated[AsyncSession, Depends(get_db)]):
    return [LlmModelOut.of(model) for model in await llm_models.list_models(db)]


@router.post("/llm-models", response_model=LlmModelOut, status_code=status.HTTP_201_CREATED)
async def add_llm_model(body: LlmModelCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    try:
        model = await llm_models.create_model(
            db, name=body.name, capability_ids=body.capability_ids, enabled=body.enabled
        )
    except llm_models.DuplicateError:
        raise _DUPLICATE from None
    except llm_models.NotFoundError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Capacité inconnue") from None
    model_router.forget()
    return LlmModelOut.of(model)


@router.put("/llm-models/order", response_model=list[LlmModelOut])
async def reorder_llm_models(body: LlmModelOrder, db: Annotated[AsyncSession, Depends(get_db)]):
    try:
        models = await llm_models.reorder_models(db, body.model_ids)
    except llm_models.NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="La liste doit contenir tous les modèles"
        ) from None
    model_router.forget()
    return [LlmModelOut.of(model) for model in models]


@router.patch("/llm-models/{model_id}", response_model=LlmModelOut)
async def update_llm_model(model_id: uuid.UUID, body: LlmModelUpdate, db: Annotated[AsyncSession, Depends(get_db)]):
    try:
        model = await llm_models.update_model(db, model_id, capability_ids=body.capability_ids, enabled=body.enabled)
    except llm_models.NotFoundError:
        raise _NOT_FOUND from None
    model_router.forget()
    return LlmModelOut.of(model)


@router.delete("/llm-models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_model(model_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    try:
        await llm_models.delete_model(db, model_id)
    except llm_models.NotFoundError:
        raise _NOT_FOUND from None
    model_router.forget()


# --- Le hub : seulement les noms ---


@router.get("/llm-hub-models", response_model=LlmHubModelsOut)
async def hub_models(db: Annotated[AsyncSession, Depends(get_db)], refresh: bool = False):
    """Les modèles que le hub sert et que la liste n'a pas encore. `refresh` relit le hub, sinon : dernière lecture."""
    try:
        names, read_at = await llm_hub.read(refresh=refresh)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Le hub LLM n'est pas configuré"
        ) from None
    registered = {model.name for model in await llm_models.list_models(db)}
    return LlmHubModelsOut(models=[name for name in names if name not in registered], read_at=read_at)


# --- Un seul modèle / auto ---


@router.get("/llm-routing", response_model=LlmRoutingOut)
async def get_routing(db: Annotated[AsyncSession, Depends(get_db)]):
    return LlmRoutingOut(auto_mode=await llm_models.auto_mode(db))


@router.put("/llm-routing", response_model=LlmRoutingOut)
async def set_routing(body: LlmRoutingOut, db: Annotated[AsyncSession, Depends(get_db)]):
    value = await llm_models.set_auto_mode(db, body.auto_mode)
    model_router.forget()
    return LlmRoutingOut(auto_mode=value)
