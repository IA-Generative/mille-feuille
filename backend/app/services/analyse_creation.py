"""Qui crée une analyse, et pour quels groupes (issue #662) : un super admin, ou qui a la permission « créer une
analyse » dans un groupe, et seulement pour ces groupes-là."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext
from app.models.analyse_access import AnalyseGroup
from app.services.analyse_access import groups_allowing
from app.services.group_names import group_names
from app.services.permissions import Permission


async def creation_groups(db: AsyncSession, user: RequestContext, wanted: list[str] | None) -> list[str]:
    allowed = await groups_allowing(db, user, Permission.ANALYSE_CREATE)
    if not user.is_admin and not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les admins d'un groupe et les super admins créent des analyses.",
        )
    if wanted is None:
        return allowed
    chosen = list(dict.fromkeys(wanted))
    # Un super admin peut choisir tout groupe existant.
    known = set(allowed) | (set(await group_names(db, chosen)) if user.is_admin else set())
    if foreign := [group for group in chosen if group not in known]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "group_not_yours", "message": "Choisissez parmi vos groupes.", "groups": foreign},
        )
    if not chosen and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "groups_required", "message": "Choisissez au moins un groupe."},
        )
    return chosen


async def grant_groups(db: AsyncSession, analyse_id: uuid.UUID, group_ids: list[str], granted_by: str) -> None:
    for group_id in group_ids:
        db.add(AnalyseGroup(analyse_id=analyse_id, group_id=group_id, granted_by=granted_by))
    await db.commit()
