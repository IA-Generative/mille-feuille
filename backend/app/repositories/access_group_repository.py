"""Groupes, rôles et membres (issue #659) : les règles tenues ici, quel que soit l'appelant. Qui a le **droit**
d'appeler ces méthodes se décide dans les routes (issue #661)."""

import uuid
from collections.abc import Collection, Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import email_index
from app.core.security.factory import RequestContext
from app.models.access_group import (
    AccessVersion,
    AppGroup,
    AppGroupEvent,
    AppGroupEventType,
    AppGroupMember,
    AppRole,
)
from app.models.analyse_access import AnalyseGroup, AnalysePerson
from app.models.analyse_share import AnalyseShare
from app.models.app_user import AppUser
from app.models.dossier_access import DossierGroupAccess
from app.models.knowledge_source import KnowledgeSource
from app.models.tool import ToolServer
from app.repositories.user_directory_repository import display_name
from app.services.memberships import sync_directory_groups
from app.services.permissions import Permission
from app.utils.sorting import sort_key


class NameTakenError(Exception):
    """Un autre groupe, ou un autre rôle, porte déjà ce nom."""


class SystemRoleError(Exception):
    """Un rôle fourni par l'application ne se modifie ni ne se supprime."""


class InUseError(Exception):
    """Un groupe qui a des membres, ou un rôle attribué, ne se supprime pas."""


class AlreadyMemberError(Exception):
    pass


class UnknownPermissionError(ValueError):
    pass


def permissions_of(role: AppRole) -> set[Permission]:
    """Un rôle fourni a toutes les permissions, y compris celles ajoutées après sa création."""
    if role.system:
        return set(Permission)
    return {Permission(value) for value in role.permissions if value in set(Permission)}


def _checked(permissions: Collection[str]) -> list[str]:
    unknown = sorted(set(permissions) - set(Permission))
    if unknown:
        raise UnknownPermissionError(", ".join(unknown))
    return [p.value for p in Permission if p in permissions]


class AccessGroupRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # --- Groupes ---

    async def list_groups(self) -> Sequence[AppGroup]:
        query = select(AppGroup).order_by(func.lower(AppGroup.name)).execution_options(populate_existing=True)
        return (await self.db.execute(query)).scalars().all()

    async def get_group(self, group_id: uuid.UUID) -> AppGroup | None:
        return await self.db.get(AppGroup, group_id, populate_existing=True)

    async def create_group(self, *, name: str, description: str, actor: RequestContext) -> AppGroup:
        group = AppGroup(id=uuid.uuid4(), name=name, description=description, created_by=actor.user_id)
        self.db.add(group)
        self._log(group.id, AppGroupEventType.GROUP_CREATED, actor)
        await self._commit_name()
        return await self.get_group(group.id)

    async def update_group(self, group: AppGroup, *, name: str, description: str, actor: RequestContext) -> AppGroup:
        if self._replace(group, {"name": name, "description": description}, actor):
            self._log(group.id, AppGroupEventType.GROUP_UPDATED, actor)
        await self._commit_name()
        return await self.get_group(group.id)

    async def restore_group(self, group: AppGroup, version_id: uuid.UUID, actor: RequestContext) -> AppGroup | None:
        version = next((v for v in group.versions if v.id == version_id), None)
        if version is None:
            return None
        values = {"name": group.name, "description": group.description, version.field: version.content}
        return await self.update_group(group, actor=actor, **values)

    async def is_group_used(self, group_id: uuid.UUID) -> bool:
        """Des membres, ou un dossier, un serveur d'outils, une source ou un partage qui s'y réfère."""
        key = str(group_id)
        for query in (
            select(AppGroupMember.id).where(AppGroupMember.group_id == group_id),
            select(DossierGroupAccess.dossier_id).where(DossierGroupAccess.group_id == key),
            select(ToolServer.id).where(ToolServer.groups.has_any(array([key]))),
            select(KnowledgeSource.id).where(KnowledgeSource.groups.has_any(array([key]))),
            select(AnalyseShare.id).where(AnalyseShare.keycloak_group == key),
            select(AnalyseGroup.analyse_id).where(AnalyseGroup.group_id == key),
        ):
            if await self.db.scalar(query.limit(1)) is not None:
                return True
        return False

    async def delete_group(self, group: AppGroup, actor: RequestContext) -> None:
        if await self.is_group_used(group.id):
            raise InUseError
        self._log(group.id, AppGroupEventType.GROUP_DELETED, actor)
        await self.db.delete(group)
        await self.db.commit()

    # --- Rôles ---

    async def list_roles(self) -> Sequence[AppRole]:
        query = select(AppRole).execution_options(populate_existing=True)
        roles = (await self.db.execute(query)).scalars().all()
        return sorted(roles, key=lambda r: (not r.system, sort_key(r.name)))

    async def get_role(self, role_id: uuid.UUID) -> AppRole | None:
        return await self.db.get(AppRole, role_id, populate_existing=True)

    async def create_role(
        self, *, name: str, description: str, permissions: Collection[str], actor: RequestContext
    ) -> AppRole:
        role = AppRole(
            id=uuid.uuid4(),
            name=name,
            description=description,
            permissions=_checked(permissions),
            created_by=actor.user_id,
        )
        self.db.add(role)
        await self._commit_name()
        return await self.get_role(role.id)

    async def update_role(
        self, role: AppRole, *, name: str, description: str, permissions: Collection[str], actor: RequestContext
    ) -> AppRole:
        if role.system:
            raise SystemRoleError
        self._replace(role, {"name": name, "description": description, "permissions": _checked(permissions)}, actor)
        await self._commit_name()
        return await self.get_role(role.id)

    async def restore_role(self, role: AppRole, version_id: uuid.UUID, actor: RequestContext) -> AppRole | None:
        version = next((v for v in role.versions if v.id == version_id), None)
        if version is None:
            return None
        values = {"name": role.name, "description": role.description, "permissions": role.permissions}
        values[version.field] = version.content
        # Une permission retirée de la liste depuis cette version n'est pas ressuscitée.
        values["permissions"] = [p for p in values["permissions"] if p in set(Permission)]
        return await self.update_role(role, actor=actor, **values)

    async def is_role_used(self, role_id: uuid.UUID) -> bool:
        for model in (AppGroupMember, AnalysePerson):
            if await self.db.scalar(select(model.id).where(model.role_id == role_id).limit(1)) is not None:
                return True
        return False

    async def delete_role(self, role: AppRole) -> None:
        if role.system:
            raise SystemRoleError
        if await self.is_role_used(role.id):
            raise InUseError
        await self.db.delete(role)
        await self.db.commit()

    # --- Droits ---

    async def permissions_in(self, user: RequestContext, group_id: uuid.UUID) -> set[Permission]:
        """Ce que la personne peut faire dans ce groupe ; un super admin peut tout."""
        if user.is_admin:
            return set(Permission)
        role = await self.db.scalar(
            select(AppRole)
            .join(AppGroupMember, AppGroupMember.role_id == AppRole.id)
            .where(AppGroupMember.group_id == group_id, AppGroupMember.user_id == user.user_id)
        )
        return permissions_of(role) if role else set()

    # --- Membres ---

    async def member_counts(self) -> dict[uuid.UUID, int]:
        query = select(AppGroupMember.group_id, func.count()).group_by(AppGroupMember.group_id)
        return {group_id: count for group_id, count in await self.db.execute(query)}

    async def get_member(self, group_id: uuid.UUID, member_id: uuid.UUID) -> AppGroupMember | None:
        member = await self.db.get(AppGroupMember, member_id)
        return member if member and member.group_id == group_id else None

    async def people(self, user_ids: Collection[str]) -> dict[str, AppUser]:
        if not user_ids:
            return {}
        rows = await self.db.scalars(select(AppUser).where(AppUser.user_id.in_(list(user_ids))))
        return {person.user_id: person for person in rows}

    async def members(self, group_id: uuid.UUID) -> Sequence[AppGroupMember]:
        query = (
            select(AppGroupMember)
            .where(AppGroupMember.group_id == group_id)
            .order_by(AppGroupMember.created_at, AppGroupMember.id)
        )
        return (await self.db.execute(query)).scalars().all()

    async def add_member(
        self,
        group: AppGroup,
        role: AppRole,
        *,
        actor: RequestContext,
        email: str | None = None,
        user_id: str | None = None,
    ) -> AppGroupMember:
        """`user_id` : une personne choisie dans l'annuaire ; sinon une adresse, à rattacher plus tard. Une adresse
        n'est **pas** rapprochée d'un compte ici : seule une adresse vérifiée à la connexion le permettra (#660)."""
        address = (email or "").strip().lower() or None
        if address is None and user_id is None:
            raise ValueError("Une adresse ou un compte est nécessaire")
        index = email_index(address) if address else None
        same = [
            condition
            for condition, value in (
                (AppGroupMember.email_index == index, index),
                (AppGroupMember.user_id == user_id, user_id),
            )
            if value is not None
        ]
        if await self.db.scalar(select(AppGroupMember.id).where(AppGroupMember.group_id == group.id, or_(*same))):
            raise AlreadyMemberError
        member = AppGroupMember(
            group_id=group.id,
            role_id=role.id,
            user_id=user_id,
            email=address,
            email_index=index,
            added_by=actor.user_id,
        )
        self.db.add(member)
        self._log(group.id, AppGroupEventType.MEMBER_ADDED, actor, member=member, role_name=role.name)
        try:
            if user_id:
                await sync_directory_groups(self.db, user_id)
            await self.db.commit()
        except IntegrityError as error:  # ajout simultané de la même personne
            await self.db.rollback()
            raise AlreadyMemberError from error
        return member

    async def set_member_role(self, member: AppGroupMember, role: AppRole, actor: RequestContext) -> AppGroupMember:
        if member.role_id == role.id:
            return member
        previous = await self.get_role(member.role_id)
        member.role_id = role.id
        self._log(
            member.group_id,
            AppGroupEventType.MEMBER_ROLE_CHANGED,
            actor,
            member=member,
            role_name=role.name,
            previous_role_name=previous.name,
        )
        await self.db.commit()
        return member

    async def remove_member(self, member: AppGroupMember, actor: RequestContext) -> None:
        role = await self.get_role(member.role_id)
        self._log(member.group_id, AppGroupEventType.MEMBER_REMOVED, actor, member=member, role_name=role.name)
        await self.db.delete(member)
        if member.user_id:
            await sync_directory_groups(self.db, member.user_id)
        await self.db.commit()

    async def events(self, group_id: uuid.UUID) -> Sequence[AppGroupEvent]:
        query = (
            select(AppGroupEvent)
            .where(AppGroupEvent.group_id == group_id)
            .order_by(AppGroupEvent.created_at.desc(), AppGroupEvent.id)
        )
        return (await self.db.execute(query)).scalars().all()

    # --- Interne ---

    def _replace(self, target: AppGroup | AppRole, values: dict, actor: RequestContext) -> bool:
        """Remplace les champs qui changent, en gardant l'ancienne valeur de chacun."""
        changed = False
        for field, value in values.items():
            previous = getattr(target, field)
            if value != previous:
                target.versions.append(AccessVersion(field=field, content=previous, author_id=actor.user_id))
                setattr(target, field, value)
                changed = True
        return changed

    def _log(
        self,
        group_id: uuid.UUID,
        type_: AppGroupEventType,
        actor: RequestContext,
        *,
        member: AppGroupMember | None = None,
        role_name: str | None = None,
        previous_role_name: str | None = None,
    ) -> None:
        self.db.add(
            AppGroupEvent(
                group_id=group_id,
                type=type_.value,
                actor_id=actor.user_id,
                actor_name=display_name(actor),
                subject_user_id=member.user_id if member else None,
                subject_email=member.email if member else None,
                role_name=role_name,
                previous_role_name=previous_role_name,
            )
        )

    async def _commit_name(self) -> None:
        try:
            await self.db.commit()
        except IntegrityError as error:
            await self.db.rollback()
            raise NameTakenError from error
