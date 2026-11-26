import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.admin import require_admin
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.models.analyse_theme import AnalyseTheme
from app.repositories.analyse_theme_repository import AnalyseThemeRepository, ThemeNameTakenError
from app.schemas.analyse_theme import AnalyseThemeIn, AnalyseThemeList, AnalyseThemeOut

router = APIRouter(prefix="/analyse-themes", tags=["Analyses"], dependencies=[Depends(get_current_user)])


async def _get_or_404(repository: AnalyseThemeRepository, theme_id: uuid.UUID) -> AnalyseTheme:
    theme = await repository.get(theme_id)
    if theme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thème introuvable")
    return theme


def _name_taken() -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Un thème porte déjà ce nom.")


async def _with_count(repository: AnalyseThemeRepository, theme: AnalyseTheme) -> AnalyseThemeOut:
    counts = await repository.analyse_counts()
    return repository.to_schema(theme, counts.get(theme.id, 0))


@router.get("", response_model=AnalyseThemeList)
async def list_themes(
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[str | None, Query(description="Recherche : les compteurs ne portent que sur elle")] = None,
) -> AnalyseThemeList:
    repository = AnalyseThemeRepository(db)
    themes = await repository.list_all()
    counts = await repository.analyse_counts(q)
    return AnalyseThemeList(
        items=[repository.to_schema(theme, counts.get(theme.id, 0)) for theme in themes],
        unthemed_count=counts.get(None, 0),
    )


@router.post("", response_model=AnalyseThemeOut, status_code=status.HTTP_201_CREATED)
async def create_theme(
    body: AnalyseThemeIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(require_admin)],
) -> AnalyseThemeOut:
    repository = AnalyseThemeRepository(db)
    try:
        theme = await repository.create(name=body.name, description=body.description, created_by=user.user_id or None)
    except ThemeNameTakenError as error:
        raise _name_taken() from error
    return repository.to_schema(theme, 0)


@router.put("/{theme_id}", response_model=AnalyseThemeOut, dependencies=[Depends(require_admin)])
async def update_theme(
    theme_id: uuid.UUID, body: AnalyseThemeIn, db: Annotated[AsyncSession, Depends(get_db)]
) -> AnalyseThemeOut:
    repository = AnalyseThemeRepository(db)
    theme = await _get_or_404(repository, theme_id)
    try:
        theme = await repository.update(theme, name=body.name, description=body.description)
    except ThemeNameTakenError as error:
        raise _name_taken() from error
    return await _with_count(repository, theme)


@router.post(
    "/{theme_id}/versions/{version_id}/restore",
    response_model=AnalyseThemeOut,
    dependencies=[Depends(require_admin)],
)
async def restore_theme_version(
    theme_id: uuid.UUID, version_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> AnalyseThemeOut:
    """Restaure un ancien nom ou une ancienne description ; la valeur courante devient elle-même une version."""
    repository = AnalyseThemeRepository(db)
    theme = await _get_or_404(repository, theme_id)
    version = next((v for v in theme.versions if v.id == version_id), None)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version introuvable")
    values = {"name": theme.name, "description": theme.description, version.field: version.content}
    try:
        theme = await repository.update(theme, **values)
    except ThemeNameTakenError as error:
        raise _name_taken() from error
    return await _with_count(repository, theme)


@router.delete("/{theme_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
async def delete_theme(theme_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> Response:
    """Supprime le thème ; ses analyses sont conservées, sans thème."""
    repository = AnalyseThemeRepository(db)
    await repository.delete(await _get_or_404(repository, theme_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
