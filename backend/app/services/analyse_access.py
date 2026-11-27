"""Qui voit une analyse (issue #662). **Une seule règle**, partagée par les dépôts et la garde des routes :

- un **super admin** voit tout ;
- les membres d'un **groupe associé** à l'analyse la voient ;
- une personne **ajoutée** à l'analyse la voit ;
- une analyse sans groupe ni personne n'est vue que des super admins. Le créateur n'a aucun droit propre.
"""

import uuid
from collections.abc import Collection
from typing import TYPE_CHECKING

from sqlalchemy import ColumnElement, exists, false, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_group import AppGroupMember, AppRole
from app.models.analyse import Analyse
from app.models.analyse_access import AnalyseGroup, AnalysePerson
from app.services.permissions import Permission

if TYPE_CHECKING:
    from app.core.security.factory import RequestContext


def membership_clause(analyse_id: ColumnElement, user_id: str, groups: Collection[str]) -> ColumnElement[bool]:
    """« La personne a accès à l'analyse `analyse_id` » hors super admin, corrélée à la requête englobante."""
    by_group = (
        exists(
            select(1).where(AnalyseGroup.analyse_id == analyse_id, AnalyseGroup.group_id.in_(list(groups)))
        ).correlate_except(AnalyseGroup)
        if groups
        else false()
    )
    added = exists(
        select(1).where(AnalysePerson.analyse_id == analyse_id, AnalysePerson.user_id == user_id)
    ).correlate_except(AnalysePerson)
    return or_(by_group, added)


def visible_analyses(user: "RequestContext") -> ColumnElement[bool]:
    """Condition SQL à ajouter au `where` d'une requête sur `Analyse`."""
    return true() if user.is_admin else membership_clause(Analyse.id, user.user_id, user.groups)


async def has_membership(db: AsyncSession, analyse_id: uuid.UUID, user_id: str, groups: Collection[str]) -> bool:
    query = select(Analyse.id).where(Analyse.id == analyse_id, membership_clause(Analyse.id, user_id, groups))
    return await db.scalar(query) is not None


async def can_see_analyse(db: AsyncSession, analyse_id: uuid.UUID, user: "RequestContext") -> bool:
    return user.is_admin or await has_membership(db, analyse_id, user.user_id, user.groups)


async def groups_allowing(db: AsyncSession, user: "RequestContext", permission: Permission) -> list[str]:
    """Les groupes de la personne où son rôle donne cette permission ; tous ses groupes pour un super admin."""
    if user.is_admin:
        return list(user.groups)
    rows = await db.execute(
        select(AppGroupMember.group_id, AppRole.permissions, AppRole.system)
        .join(AppRole, AppRole.id == AppGroupMember.role_id)
        .where(AppGroupMember.user_id == user.user_id)
    )
    return sorted(
        str(group_id)
        for group_id, permissions, system in rows
        if (system or permission.value in permissions) and str(group_id) in user.groups
    )
