"""Les modèles LLM connus de l'application, leurs capacités et le réglage du choix du modèle : lecture, et ajout,
modification, suppression par un administrateur."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_model import LlmCapabilityConfig, LlmModelConfig, LlmRoutingSettings


class DuplicateError(Exception):
    """Un modèle ou une capacité de ce nom existe déjà."""


class NotFoundError(Exception):
    pass


# --- Capacités ---


async def list_capabilities(db: AsyncSession) -> list[LlmCapabilityConfig]:
    return list((await db.scalars(select(LlmCapabilityConfig).order_by(LlmCapabilityConfig.name))).all())


async def _capability(db: AsyncSession, capability_id: uuid.UUID) -> LlmCapabilityConfig:
    capability = await db.get(LlmCapabilityConfig, capability_id)
    if capability is None:
        raise NotFoundError
    return capability


async def create_capability(db: AsyncSession, *, name: str, description: str) -> LlmCapabilityConfig:
    capability = LlmCapabilityConfig(name=name, description=description)
    db.add(capability)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise DuplicateError from None
    await db.refresh(capability)
    return capability


async def update_capability(db: AsyncSession, capability_id: uuid.UUID, changes: dict) -> LlmCapabilityConfig:
    capability = await _capability(db, capability_id)
    for key, value in changes.items():
        setattr(capability, key, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise DuplicateError from None
    await db.refresh(capability)
    return capability


async def delete_capability(db: AsyncSession, capability_id: uuid.UUID) -> None:
    """Supprime la capacité ; elle est retirée de tous les modèles (cascade)."""
    await db.delete(await _capability(db, capability_id))
    await db.commit()


# --- Modèles ---


async def list_models(db: AsyncSession) -> list[LlmModelConfig]:
    return list((await db.scalars(select(LlmModelConfig).order_by(LlmModelConfig.position, LlmModelConfig.name))).all())


async def enabled_models(db: AsyncSession) -> list[LlmModelConfig]:
    """Les modèles actifs, le préféré d'abord."""
    return [model for model in await list_models(db) if model.enabled]


async def _model(db: AsyncSession, model_id: uuid.UUID) -> LlmModelConfig:
    model = await db.get(LlmModelConfig, model_id)
    if model is None:
        raise NotFoundError
    return model


async def _capabilities_of(db: AsyncSession, capability_ids: list[uuid.UUID]) -> list[LlmCapabilityConfig]:
    ids = set(capability_ids)
    found = list((await db.scalars(select(LlmCapabilityConfig).where(LlmCapabilityConfig.id.in_(ids)))).all())
    if len(found) != len(ids):
        raise NotFoundError
    return found


async def create_model(
    db: AsyncSession,
    *,
    name: str,
    capability_ids: list[uuid.UUID],
    enabled: bool = True,
    types: list[str] | None = None,
) -> LlmModelConfig:
    existing = await list_models(db)
    if any(model.name == name for model in existing):
        raise DuplicateError
    # Un nouveau modèle passe après les autres : il ne devient pas le modèle par défaut sans qu'on le demande.
    model = LlmModelConfig(
        name=name,
        enabled=enabled,
        types=types,
        position=max((model.position for model in existing), default=-1) + 1,
        capabilities=await _capabilities_of(db, capability_ids),
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return model


async def update_model(
    db: AsyncSession, model_id: uuid.UUID, *, capability_ids: list[uuid.UUID] | None = None, enabled: bool | None = None
) -> LlmModelConfig:
    model = await _model(db, model_id)
    if capability_ids is not None:
        model.capabilities = await _capabilities_of(db, capability_ids)
    if enabled is not None:
        model.enabled = enabled
    await db.commit()
    await db.refresh(model)
    return model


async def set_detected_types(db: AsyncSession, by_name: dict[str, list[str]]) -> None:
    """Met à jour les types des modèles enregistrés d'après la dernière lecture du hub (qui les révèle : on ne les
    saisit pas)."""
    changed = False
    for model in await list_models(db):
        if model.name in by_name and model.types != by_name[model.name]:
            model.types = by_name[model.name]
            changed = True
    if changed:
        await db.commit()


def can_complete(model: LlmModelConfig) -> bool:
    """Le modèle peut-il répondre à du texte ? Vrai aussi quand ses types ne sont pas encore lus : on ne l'écarte pas
    sur une absence d'information."""
    return model.types is None or "completion" in model.types


async def reorder_models(db: AsyncSession, model_ids: list[uuid.UUID]) -> list[LlmModelConfig]:
    """Range les modèles dans cet ordre (le premier devient le modèle par défaut). `model_ids` les contient tous."""
    models = {model.id: model for model in await list_models(db)}
    if set(model_ids) != set(models) or len(model_ids) != len(models):
        raise NotFoundError
    for position, model_id in enumerate(model_ids):
        models[model_id].position = position
    await db.commit()
    return await list_models(db)


async def delete_model(db: AsyncSession, model_id: uuid.UUID) -> None:
    await db.delete(await _model(db, model_id))
    await db.commit()


# --- Réglage du choix du modèle ---


async def auto_mode(db: AsyncSession) -> bool:
    row = await db.get(LlmRoutingSettings, 1)
    return bool(row and row.auto_mode)


async def set_auto_mode(db: AsyncSession, value: bool) -> bool:
    row = await db.get(LlmRoutingSettings, 1)
    if row is None:
        db.add(LlmRoutingSettings(id=1, auto_mode=value))
    else:
        row.auto_mode = value
    await db.commit()
    return value
