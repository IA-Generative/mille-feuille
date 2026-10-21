from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext, get_current_user
from app.core.security.internal import verify_app_token
from app.db import get_db
from app.schemas.usage import UsageIn, UsageOut
from app.services.usage_service import NotAdminError, UsageService

router = APIRouter(tags=["Usage"])
internal_router = APIRouter(prefix="/internal", tags=["Internal", "Usage"], dependencies=[Depends(verify_app_token)])


def get_usage_service(db: Annotated[AsyncSession, Depends(get_db)]) -> UsageService:
    return UsageService(db)


ServiceDep = Annotated[UsageService, Depends(get_usage_service)]
UserDep = Annotated[RequestContext, Depends(get_current_user)]
DaysQuery = Annotated[int, Query(ge=1, le=365)]


@router.get(
    "/usage/me",
    summary="Tokens consommés pour moi, au total et par tâche, jour et modèle",
    response_model=UsageOut,
)
async def my_usage(user: UserDep, service: ServiceDep, days: DaysQuery = 30) -> UsageOut:
    return await service.mine(user, days)


@router.get(
    "/admin/usage",
    summary="Consommation de tout le monde, ou d'une personne (user_id), avec le détail par personne",
    response_model=UsageOut,
)
async def overall_usage(
    user: UserDep, service: ServiceDep, days: DaysQuery = 30, user_id: str | None = None
) -> UsageOut:
    try:
        return await service.overall(user, days, user_id)
    except NotAdminError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Accès réservé aux administrateurs"
        ) from error


@internal_router.post(
    "/usage",
    summary="Un worker dépose les tokens d'un appel au LLM (compteurs seulement)",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def record_usage(body: UsageIn, service: ServiceDep) -> None:
    await service.record(body)
