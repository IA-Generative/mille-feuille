"""Ce que la personne connectée peut faire sur un dossier ou une analyse (issue #664) : l'interface s'en sert pour
masquer ou désactiver. Le contrôle reste celui des gardes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analyse_guard import require_analyse_visible
from app.core.dossier_guard import require_dossier_visible
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.services import role_permissions
from app.services.permissions import Permission

router = APIRouter(tags=["Groupes et rôles"])

Db = Annotated[AsyncSession, Depends(get_db)]
User = Annotated[RequestContext, Depends(get_current_user)]


class PermissionsOut(BaseModel):
    permissions: list[Permission]


def _out(granted: set[Permission]) -> PermissionsOut:
    return PermissionsOut(permissions=[p for p in Permission if p in granted])


@router.get(
    "/dossiers/{dossier_id}/permissions",
    response_model=PermissionsOut,
    dependencies=[Depends(require_dossier_visible)],
)
async def dossier_permissions(dossier_id: uuid.UUID, db: Db, user: User) -> PermissionsOut:
    return _out(await role_permissions.dossier_permissions(db, dossier_id, user))


@router.get(
    "/analyses/{analyse_id}/permissions",
    response_model=PermissionsOut,
    dependencies=[Depends(require_analyse_visible)],
)
async def analyse_permissions(analyse_id: uuid.UUID, db: Db, user: User) -> PermissionsOut:
    return _out(await role_permissions.analyse_permissions(db, analyse_id, user))
