import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.analysis_agents import load_agents
from app.core.dossier_guard import require_dossier_visible
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.repositories.dossier_repository import DossierRepository
from app.schemas.chat_agent import ChatAgentOut

# Même garde que les routes `/dossiers/{id}/…` : 404 pour qui ne voit pas le dossier.
router = APIRouter(
    prefix="/dossiers", tags=["Agents"], dependencies=[Depends(get_current_user), Depends(require_dossier_visible)]
)


@router.get("/{dossier_id}/agents", response_model=list[ChatAgentOut])
async def list_dossier_agents(
    dossier_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> list[ChatAgentOut]:
    """Les agents de l'analyse du dossier, dans l'ordre de l'analyse : ceux qu'on peut interroger dans le chat (en les
    nommant avec `@Nom`, ou en laissant le chat choisir)."""
    dossier = await DossierRepository(db).get(dossier_id, user)
    if dossier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")
    agents = await load_agents(str(dossier.analyse_id)) if dossier.analyse_id else []
    return [ChatAgentOut(name=agent.name, role=agent.summary) for agent in agents]
