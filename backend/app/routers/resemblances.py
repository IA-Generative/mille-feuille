import logging
import uuid
from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runner import agent_runner
from app.config import ResemblanceSettings
from app.core.security.admin import require_admin
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.models.resemblance import ResemblanceTheme
from app.repositories.resemblance_repository import (
    DismissalForbiddenError,
    GroupNotFoundError,
    ResemblanceRepository,
    UnknownEntityError,
)
from app.schemas.resemblance import (
    EntityOut,
    GroupPageOut,
    SuggestionsIn,
    SuggestionsOut,
    ThemeIn,
    ThemeListOut,
    ThemeOut,
)
from app.services.resemblance import compute, entity_index

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resemblances", tags=["Search"], dependencies=[Depends(get_current_user)])

Db = Annotated[AsyncSession, Depends(get_db)]
User = Annotated[RequestContext, Depends(get_current_user)]
Admin = Annotated[RequestContext, Depends(require_admin)]


def dispatch_compute(theme_id: uuid.UUID) -> None:
    agent_runner.start(f"resemblance:{theme_id}", partial(compute.run_theme, str(theme_id)))


async def _theme_or_404(repository: ResemblanceRepository, theme_id: uuid.UUID, user: RequestContext):
    theme = await repository.get(theme_id)
    # Un thème désactivé n'existe que pour qui peut le réactiver.
    if theme is None or (not theme.active and not user.is_admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thème de ressemblance introuvable")
    return theme


async def _out(repository: ResemblanceRepository, theme: ResemblanceTheme, user: RequestContext) -> ThemeOut:
    return repository.to_schema(theme, user, known=await repository.known_entities_of(theme))


@router.get("/themes", response_model=ThemeListOut)
async def list_themes(db: Db, user: User) -> ThemeListOut:
    return ThemeListOut(
        enabled=ResemblanceSettings().RESEMBLANCE_ENABLED, items=await ResemblanceRepository(db).list_for(user)
    )


@router.post("/themes", response_model=ThemeOut, status_code=status.HTTP_201_CREATED)
async def create_theme(body: ThemeIn, db: Db, user: Admin) -> ThemeOut:
    repository = ResemblanceRepository(db)
    try:
        theme = await repository.create(body, user)
    except UnknownEntityError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    dispatch_compute(theme.id)
    return await _out(repository, theme, user)


async def _replace(repository: ResemblanceRepository, theme, content: dict, user: RequestContext) -> ThemeOut:
    try:
        theme = await repository.update(theme, content, user)
    except UnknownEntityError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    dispatch_compute(theme.id)
    return await _out(repository, theme, user)


@router.put("/themes/{theme_id}", response_model=ThemeOut)
async def update_theme(theme_id: uuid.UUID, body: ThemeIn, db: Db, user: Admin) -> ThemeOut:
    repository = ResemblanceRepository(db)
    theme = await _theme_or_404(repository, theme_id, user)
    return await _replace(repository, theme, body.model_dump(mode="json"), user)


@router.post("/themes/{theme_id}/versions/{version_id}/restore", response_model=ThemeOut)
async def restore_theme(theme_id: uuid.UUID, version_id: uuid.UUID, db: Db, user: Admin) -> ThemeOut:
    repository = ResemblanceRepository(db)
    theme = await _theme_or_404(repository, theme_id, user)
    version = next((v for v in theme.versions if v.id == version_id), None)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version introuvable")
    return await _replace(repository, theme, dict(version.content), user)


@router.delete("/themes/{theme_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_theme(theme_id: uuid.UUID, db: Db, user: Admin) -> Response:
    repository = ResemblanceRepository(db)
    await repository.delete(await _theme_or_404(repository, theme_id, user))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/themes/{theme_id}/compute", status_code=status.HTTP_202_ACCEPTED)
async def recompute_theme(theme_id: uuid.UUID, db: Db, user: Admin) -> Response:
    await _theme_or_404(ResemblanceRepository(db), theme_id, user)
    dispatch_compute(theme_id)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get("/themes/{theme_id}/groups", response_model=GroupPageOut)
async def list_groups(
    theme_id: uuid.UUID,
    db: Db,
    user: User,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
    dismissed: bool = False,
) -> GroupPageOut:
    repository = ResemblanceRepository(db)
    theme = await _theme_or_404(repository, theme_id, user)
    return await repository.groups(theme, user, page=page, page_size=page_size, dismissed=dismissed)


async def _set_dismissed(db: AsyncSession, theme_id: uuid.UUID, key: str, user: RequestContext, dismissed: bool):
    repository = ResemblanceRepository(db)
    theme = await _theme_or_404(repository, theme_id, user)
    try:
        await repository.set_dismissed(theme, key, user, dismissed=dismissed)
    except GroupNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rapprochement introuvable") from error
    except DismissalForbiddenError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Votre rôle ne permet pas cette action.") from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/themes/{theme_id}/groups/{key}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_group(theme_id: uuid.UUID, key: str, db: Db, user: User) -> Response:
    return await _set_dismissed(db, theme_id, key, user, True)


@router.post("/themes/{theme_id}/groups/{key}/restore", status_code=status.HTTP_204_NO_CONTENT)
async def restore_group(theme_id: uuid.UUID, key: str, db: Db, user: User) -> Response:
    return await _set_dismissed(db, theme_id, key, user, False)


@router.get("/entities", response_model=list[EntityOut], dependencies=[Depends(require_admin)])
async def list_entities(db: Db) -> list[EntityOut]:
    """Les entités définies dans toutes les analyses, pour composer les critères."""
    return await ResemblanceRepository(db).entities()


@router.post("/entities/suggestions", response_model=SuggestionsOut, dependencies=[Depends(require_admin)])
async def suggest_entities(body: SuggestionsIn, db: Db) -> SuggestionsOut:
    """Les entités dont la définition ressemble à celles données, ou à une description. Une proposition seulement."""
    if not entity_index.available():
        return SuggestionsOut(available=False, items=[])
    entities = {str(e.id): e for e in await ResemblanceRepository(db).entities()}
    indexed = [entity_index.IndexedEntity(i, e.name, e.definition, e.type) for i, e in entities.items()]
    try:
        found = await entity_index.suggest(indexed, entity_ids=[str(i) for i in body.entity_ids], text=body.text)
    except Exception as error:
        logger.error("Propositions d'entités indisponibles : %s", type(error).__name__)
        return SuggestionsOut(available=False, items=[])
    return SuggestionsOut(available=True, items=[entities[i] for i in found if i in entities])
