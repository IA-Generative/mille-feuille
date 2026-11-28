import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.repositories.dossier_search_repository import DossierSearchRepository
from app.schemas.dossier_search import DossierSearchIn, DossierSearchOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["Search"], dependencies=[Depends(get_current_user)])


@router.post("", response_model=DossierSearchOut)
async def search_dossiers(
    payload: DossierSearchIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> DossierSearchOut:
    """Cherche dans les dossiers visibles de la personne. Un `POST` : les mots cherchés, souvent des noms de personnes,
    ne doivent apparaître ni dans l'URL ni dans les journaux."""
    try:
        return await DossierSearchRepository(db).search(user=user, query=payload.query, limit=payload.limit)
    except SQLAlchemyError as error:
        # Le message d'une erreur SQL reprend les paramètres, donc les mots cherchés : on ne garde que son type.
        logger.error("Recherche de dossiers en échec : %s", type(error).__name__)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "La recherche a échoué, réessayez.") from None
