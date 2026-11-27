"""Ce que les rôles permettent (issue #664) : la permission vient du rôle porté dans un groupe associé, ou du rôle donné
sur l'analyse ; plusieurs rôles s'additionnent ; un super admin peut tout.

La **visibilité** se décide ailleurs (`analyse_access`, `dossier_access`) : ces fonctions ne servent qu'une fois qu'on
sait que la personne voit l'objet."""

import uuid
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext
from app.models.access_group import AppGroupMember, AppRole
from app.models.analyse_access import AnalyseGroup, AnalysePerson
from app.models.dossier import Dossier
from app.models.dossier_access import DossierGroupAccess, Visibility
from app.services.permissions import Permission


def _of(rows) -> set[Permission]:
    granted: set[Permission] = set()
    for permissions, system in rows:
        granted |= set(Permission) if system else {p for p in Permission if p.value in permissions}
    return granted


def _group_ids(keys: Collection[str]) -> list[uuid.UUID]:
    ids = []
    for key in keys:
        try:
            ids.append(uuid.UUID(key))
        except ValueError:
            continue
    return ids


async def group_permissions(db: AsyncSession, user: RequestContext, groups: Collection[str]) -> set[Permission]:
    """Les permissions des rôles que la personne porte dans ces groupes."""
    if user.is_admin:
        return set(Permission)
    mine = _group_ids(set(groups) & set(user.groups))
    if not mine:
        return set()
    query = (
        select(AppRole.permissions, AppRole.system)
        .join(AppGroupMember, AppGroupMember.role_id == AppRole.id)
        .where(AppGroupMember.user_id == user.user_id, AppGroupMember.group_id.in_(mine))
    )
    return _of(await db.execute(query))


async def _added_person_permissions(db: AsyncSession, user_id: str, analyse_id: uuid.UUID) -> set[Permission]:
    query = (
        select(AppRole.permissions, AppRole.system)
        .join(AnalysePerson, AnalysePerson.role_id == AppRole.id)
        .where(AnalysePerson.user_id == user_id, AnalysePerson.analyse_id == analyse_id)
    )
    return _of(await db.execute(query))


async def analyse_permissions(db: AsyncSession, analyse_id: uuid.UUID, user: RequestContext) -> set[Permission]:
    if user.is_admin:
        return set(Permission)
    groups = list(await db.scalars(select(AnalyseGroup.group_id).where(AnalyseGroup.analyse_id == analyse_id)))
    return await group_permissions(db, user, groups) | await _added_person_permissions(db, user.user_id, analyse_id)


async def dossier_permissions(db: AsyncSession, dossier_id: uuid.UUID, user: RequestContext) -> set[Permission]:
    if user.is_admin:
        return set(Permission)
    row = (await db.execute(select(Dossier.visibility, Dossier.analyse_id).where(Dossier.id == dossier_id))).first()
    if row is None:
        return set()
    visibility, analyse_id = row
    if visibility == Visibility.ANALYSE.value and analyse_id is not None:
        return await analyse_permissions(db, analyse_id, user)
    groups = list(
        await db.scalars(select(DossierGroupAccess.group_id).where(DossierGroupAccess.dossier_id == dossier_id))
    )
    granted = await group_permissions(db, user, groups)
    if analyse_id is not None:
        granted |= await _added_person_permissions(db, user.user_id, analyse_id)
    return granted
