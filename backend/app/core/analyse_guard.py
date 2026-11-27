"""Garde d'accès aux analyses (issue #662) : une dépendance pour toutes les routes `/analyses/{analyse_id}/…`, comme
`dossier_guard`. Elle répond **404** à qui ne voit pas l'analyse, avant de valider le corps de la requête."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.services.analyse_access import can_see_analyse


async def require_analyse(db: AsyncSession, analyse_id: uuid.UUID, user: RequestContext) -> None:
    """404 si la personne ne voit pas l'analyse. Partagé avec les chemins qui agissent en son nom."""
    if not await can_see_analyse(db, analyse_id, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analyse introuvable")


async def require_analyse_visible(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> None:
    raw = request.path_params.get("analyse_id")
    if raw is None:
        return
    try:
        analyse_id = uuid.UUID(str(raw))
    except ValueError:
        return  # identifiant mal formé : la route le refuse elle-même (422)
    await require_analyse(db, analyse_id, user)
