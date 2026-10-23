import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.internal import verify_app_token
from app.db import get_db
from app.models.dossier import Dossier
from app.schemas.search_index import IndexRebuildOut, RebuildReport, SearchConfigOut, SearchIndexReport
from app.services.search.index_service import RebuildNotFoundError, SearchIndexService

router = APIRouter(
    prefix="/internal", tags=["Internal", "Index de recherche"], dependencies=[Depends(verify_app_token)]
)


async def _require_dossier(db: AsyncSession, dossier_id: uuid.UUID) -> None:
    if await db.get(Dossier, dossier_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")


@router.get("/dossiers/{dossier_id}/search-config", response_model=SearchConfigOut)
async def get_search_config(dossier_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> SearchConfigOut:
    """Réglages de recherche à appliquer au dossier, index actif et reconstruction en cours."""
    await _require_dossier(db, dossier_id)
    return await SearchIndexService(db).config(dossier_id)


@router.put("/dossiers/{dossier_id}/search-index", status_code=status.HTTP_204_NO_CONTENT)
async def report_search_index(
    dossier_id: uuid.UUID, body: SearchIndexReport, db: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    """Le worker dit où en est l'indexation du dossier (en cours, prête, en erreur)."""
    await _require_dossier(db, dossier_id)
    try:
        await SearchIndexService(db).report_index(dossier_id, body)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


@router.get("/index-rebuilds/{rebuild_id}", response_model=IndexRebuildOut)
async def get_rebuild(rebuild_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> IndexRebuildOut:
    from app.models.search_index import IndexRebuild

    rebuild = await db.get(IndexRebuild, rebuild_id)
    if rebuild is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Reconstruction introuvable")
    return IndexRebuildOut.model_validate(rebuild)


@router.put("/index-rebuilds/{rebuild_id}", response_model=IndexRebuildOut)
async def report_rebuild(
    rebuild_id: uuid.UUID, body: RebuildReport, db: Annotated[AsyncSession, Depends(get_db)]
) -> IndexRebuildOut:
    """Le worker dit où en est la construction (passages écrits, bascule faite, échec)."""
    try:
        return IndexRebuildOut.model_validate(await SearchIndexService(db).report_rebuild(rebuild_id, body))
    except RebuildNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Reconstruction introuvable") from error
