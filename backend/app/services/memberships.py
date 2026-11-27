"""Les groupes d'une personne, lus en base (issue #660). Keycloak ne désigne plus que les super admins.

`AppUser.groups` en est une **copie**, pour les calculs faits sans la personne (annuaire, agent qui agit en son nom) :
elle est resynchronisée à chaque changement de membre."""

from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import email_index
from app.models.access_group import AppGroupMember
from app.models.analyse_access import AnalysePerson
from app.models.app_user import AppUser

if TYPE_CHECKING:
    from app.core.security.factory import RequestContext


async def group_ids_of(db: AsyncSession, user_id: str) -> list[str]:
    rows = await db.scalars(select(AppGroupMember.group_id).where(AppGroupMember.user_id == user_id))
    return sorted(str(group_id) for group_id in rows)


async def sync_directory_groups(db: AsyncSession, user_id: str) -> None:
    """Recopie les groupes dans l'annuaire, **sans valider** (dans la transaction de l'appelant)."""
    await db.flush()
    await db.execute(update(AppUser).where(AppUser.user_id == user_id).values(groups=await group_ids_of(db, user_id)))


async def link_pending(db: AsyncSession, user_id: str, email: str) -> None:
    """Rattache au compte les places réservées à cette adresse. À n'appeler que pour une adresse **vérifiée**."""
    await _link_analyses(db, user_id, email_index(email))
    pending = (
        await db.scalars(
            select(AppGroupMember).where(
                AppGroupMember.user_id.is_(None), AppGroupMember.email_index == email_index(email)
            )
        )
    ).all()
    if not pending:
        return
    already = set(await db.scalars(select(AppGroupMember.group_id).where(AppGroupMember.user_id == user_id)))
    for member in pending:
        if member.group_id in already:  # la personne y est déjà par son compte
            await db.delete(member)
        else:
            member.user_id = user_id
    await sync_directory_groups(db, user_id)
    await db.commit()


async def _link_analyses(db: AsyncSession, user_id: str, index: str) -> None:
    pending = (
        await db.scalars(
            select(AnalysePerson).where(AnalysePerson.user_id.is_(None), AnalysePerson.email_index == index)
        )
    ).all()
    if not pending:
        return
    already = set(await db.scalars(select(AnalysePerson.analyse_id).where(AnalysePerson.user_id == user_id)))
    for person in pending:
        if person.analyse_id in already:
            await db.delete(person)
        else:
            person.user_id = user_id
    await db.commit()


async def apply_memberships(db: AsyncSession, user: "RequestContext") -> "RequestContext":
    if user.email and user.email_verified:
        await link_pending(db, user.user_id, user.email)
    user.groups = await group_ids_of(db, user.user_id)
    return user
