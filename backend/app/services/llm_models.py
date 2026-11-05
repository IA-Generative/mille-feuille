"""Les modèles LLM connus de l'application (table `llm_models`) : lecture, et ajout, modification, suppression par un
administrateur."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_model import LlmCapability, LlmModelConfig


class DuplicateModelError(Exception):
    """Un modèle de ce nom existe déjà."""


class ModelNotFoundError(Exception):
    pass


async def list_models(db: AsyncSession) -> list[LlmModelConfig]:
    return list((await db.scalars(select(LlmModelConfig).order_by(LlmModelConfig.position, LlmModelConfig.name))).all())


async def completion_models(db: AsyncSession) -> list[LlmModelConfig]:
    """Les modèles actifs qui savent compléter du texte, le préféré d'abord."""
    return [
        model
        for model in await list_models(db)
        if model.enabled and LlmCapability.COMPLETION.value in (model.capabilities or [])
    ]


async def get(db: AsyncSession, model_id: uuid.UUID) -> LlmModelConfig:
    model = await db.get(LlmModelConfig, model_id)
    if model is None:
        raise ModelNotFoundError
    return model


async def create(
    db: AsyncSession, *, name: str, capabilities: list[str], level: int, enabled: bool = True
) -> LlmModelConfig:
    existing = await list_models(db)
    if any(model.name == name for model in existing):
        raise DuplicateModelError
    # Un nouveau modèle passe après les autres : il ne devient pas le modèle par défaut sans qu'on le demande.
    model = LlmModelConfig(
        name=name,
        capabilities=capabilities,
        level=level,
        enabled=enabled,
        position=max((model.position for model in existing), default=-1) + 1,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return model


async def update(db: AsyncSession, model_id: uuid.UUID, changes: dict) -> LlmModelConfig:
    model = await get(db, model_id)
    for key, value in changes.items():
        setattr(model, key, value)
    await db.commit()
    await db.refresh(model)
    return model


async def delete(db: AsyncSession, model_id: uuid.UUID) -> None:
    await db.delete(await get(db, model_id))
    await db.commit()
