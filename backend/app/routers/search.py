import logging
from collections.abc import Awaitable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.repositories.dossier_search_repository import DossierSearchRepository, DossiersNotVisible
from app.schemas.dossier_search import DossierLinksIn, DossierLinksOut, DossierSearchIn, DossierSearchOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["Search"], dependencies=[Depends(get_current_user)])


async def _guarded[T](search: Awaitable[T]) -> T:
    """Le message d'une erreur SQL reprend ses paramètres, donc les mots cherchés ou des valeurs extraites : on ne
    journalise que son type."""
    try:
        return await search
    except SQLAlchemyError as error:
        logger.error("Recherche de dossiers en échec : %s", type(error).__name__)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "La recherche a échoué, réessayez.") from None


@router.post("", response_model=DossierSearchOut)
async def search_dossiers(
    payload: DossierSearchIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> DossierSearchOut:
    """Cherche dans les dossiers visibles de la personne. Un `POST` : les mots cherchés, souvent des noms de personnes,
    ne doivent apparaître ni dans l'URL ni dans les journaux."""
    return await _guarded(
        DossierSearchRepository(db).search(user=user, query=payload.query, limit=payload.limit, details=payload.details)
    )


@router.post("/links", response_model=DossierLinksOut)
async def link_dossiers(
    payload: DossierLinksIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> DossierLinksOut:
    """Ce qui relie des dossiers choisis. Un dossier non visible répond 404, comme un dossier qui n'existe pas."""
    try:
        return await _guarded(
            DossierSearchRepository(db).links(
                user=user, anchor_ids=payload.dossier_ids, include_related=payload.include_related
            )
        )
    except DossiersNotVisible as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            {
                "code": "dossiers_not_found",
                "message": "Dossier introuvable",
                "dossier_ids": [str(i) for i in error.dossier_ids],
            },
        ) from None
