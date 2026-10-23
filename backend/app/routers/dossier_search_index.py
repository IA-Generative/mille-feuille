import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dossier_guard import require_dossier_visible
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.schemas.search_index import IndexRebuildOut, IndexStateOut
from app.services.search.index_service import (
    NothingToRebuildError,
    RebuildInProgressError,
    RebuildNotFoundError,
    RebuildStateError,
    SearchIndexService,
    SettingsUnresolvedError,
)

router = APIRouter(
    prefix="/dossiers",
    tags=["Index de recherche"],
    dependencies=[Depends(get_current_user), Depends(require_dossier_visible)],
)


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail={"code": code, "message": message})


@router.get("/{dossier_id}/search-index", response_model=IndexStateOut)
async def get_search_index(dossier_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> IndexStateOut:
    """État de l'index de recherche du dossier : à jour, obsolète (réglages de l'analyse changés depuis) ou absent, et
    la reconstruction en cours ou la dernière."""
    return await SearchIndexService(db).state(dossier_id)


@router.post("/{dossier_id}/search-index/rebuild", response_model=IndexRebuildOut, status_code=status.HTTP_202_ACCEPTED)
async def start_rebuild(
    dossier_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> IndexRebuildOut:
    """Reconstruit l'index du dossier avec les réglages actuels de l'analyse, à côté de l'index actif qui continue de
    répondre. À la fin, l'alias bascule ; la personne valide ensuite, ou revient à l'ancien index."""
    try:
        rebuild = await SearchIndexService(db).start_rebuild(dossier_id, user.user_id)
    except SettingsUnresolvedError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": "reglages_incomplets", "message": str(error)}
        ) from error
    except RebuildInProgressError as error:
        raise _conflict(
            "reconstruction_en_cours", "Ce dossier a déjà une reconstruction en cours ou à valider."
        ) from error
    except NothingToRebuildError as error:
        raise _conflict("index_a_jour", "L'index est déjà à jour avec les réglages de l'analyse.") from error
    return IndexRebuildOut.model_validate(rebuild)


@router.post("/{dossier_id}/search-index/rebuilds/{rebuild_id}/validate", response_model=IndexRebuildOut)
async def validate_rebuild(
    dossier_id: uuid.UUID, rebuild_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> IndexRebuildOut:
    """Valide la bascule : l'ancien index est supprimé."""
    try:
        return IndexRebuildOut.model_validate(await SearchIndexService(db).validate(dossier_id, rebuild_id))
    except RebuildNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Reconstruction introuvable") from error
    except RebuildStateError as error:
        raise _conflict("etat_incompatible", str(error)) from error


@router.post("/{dossier_id}/search-index/rebuilds/{rebuild_id}/rollback", response_model=IndexRebuildOut)
async def rollback_rebuild(
    dossier_id: uuid.UUID, rebuild_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> IndexRebuildOut:
    """Abandonne la reconstruction (en cours) ou revient à l'ancien index (basculée)."""
    try:
        return IndexRebuildOut.model_validate(await SearchIndexService(db).rollback(dossier_id, rebuild_id))
    except RebuildNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Reconstruction introuvable") from error
    except RebuildStateError as error:
        raise _conflict("etat_incompatible", str(error)) from error
