"""Routes d'administration des modèles LLM : leur nom, leurs capacités et leur niveau. Réservées aux administrateurs.

Le premier modèle de complétion actif (plus petit `position`) fait tout par défaut ; en mode auto, le niveau décide."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import model_router
from app.core.security.admin import require_admin
from app.db import get_db
from app.schemas.llm_model import LlmModelCreate, LlmModelOut, LlmModelUpdate
from app.services import llm_models

router = APIRouter(prefix="/admin/llm-models", tags=["Admin"], dependencies=[Depends(require_admin)])

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Modèle introuvable")


@router.get("", response_model=list[LlmModelOut])
async def list_llm_models(db: Annotated[AsyncSession, Depends(get_db)]):
    return await llm_models.list_models(db)


@router.post("", response_model=LlmModelOut, status_code=status.HTTP_201_CREATED)
async def add_llm_model(body: LlmModelCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    try:
        model = await llm_models.create(
            db,
            name=body.name,
            capabilities=sorted({capability.value for capability in body.capabilities}),
            level=body.level,
            enabled=body.enabled,
        )
    except llm_models.DuplicateModelError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce modèle est déjà enregistré") from None
    model_router.forget()
    return model


@router.patch("/{model_id}", response_model=LlmModelOut)
async def update_llm_model(model_id: uuid.UUID, body: LlmModelUpdate, db: Annotated[AsyncSession, Depends(get_db)]):
    try:
        model = await llm_models.update(db, model_id, body.changes())
    except llm_models.ModelNotFoundError:
        raise _NOT_FOUND from None
    model_router.forget()
    return model


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_model(model_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    try:
        await llm_models.delete(db, model_id)
    except llm_models.ModelNotFoundError:
        raise _NOT_FOUND from None
    model_router.forget()
