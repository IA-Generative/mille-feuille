from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.repositories.dashboard_repository import DashboardRepository
from app.schemas.dashboard import DashboardOut
from app.services.due_date import today_in_paris

# Tableau de bord personnel (issue #174) : ce qui est affecté à la personne connectée. Les créneaux planifiés et
# les notifications ont leurs propres routes.
router = APIRouter(prefix="/dashboard", tags=["Tableau de bord"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=DashboardOut)
async def get_dashboard(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> DashboardOut:
    """Indicateurs, urgences (échéance proche ou dépassée), autres dossiers placés dans mon agenda, mes dossiers par
    statut, dossiers non affectés et activité récente d'autres personnes sur mes dossiers. Les non affectés ne sont
    montrés qu'aux administrateurs : le rôle d'instruction (#178) élargira ce droit."""
    repository = DashboardRepository(db)
    urgencies, others = await repository.agenda(user)
    return DashboardOut(
        stats=await repository.stats(user, today_in_paris()),
        urgencies=urgencies,
        others=others,
        status_counts=await repository.status_counts(user),
        unassigned=await repository.unassigned(user) if user.is_admin else None,
        activity=await repository.activity(user),
    )
