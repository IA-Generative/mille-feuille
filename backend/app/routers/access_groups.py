"""Groupes, rôles et membres (issue #661).

- **Super admin** (désigné par Keycloak) : crée et modifie les groupes et les rôles, et peut tout.
- **Membre** d'un groupe : le voit, avec ses membres.
- Qui a la permission « gérer les membres » ajoute, change et retire des membres, **sans pouvoir donner ou toucher un
  rôle plus large que le sien**.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.admin import require_admin
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.models.access_group import AppGroup, AppGroupMember, AppRole
from app.repositories.access_group_repository import (
    AccessGroupRepository,
    AlreadyMemberError,
    InUseError,
    NameTakenError,
    SystemRoleError,
    permissions_of,
)
from app.schemas.access_group import (
    AccessVersionOut,
    GroupEventOut,
    GroupIn,
    GroupName,
    GroupOut,
    MemberIn,
    MemberOut,
    MemberRoleIn,
    RoleIn,
    RoleOut,
)
from app.services.group_names import group_names
from app.services.permissions import Permission

groups_router = APIRouter(prefix="/groups", tags=["Groupes et rôles"], dependencies=[Depends(get_current_user)])
roles_router = APIRouter(prefix="/roles", tags=["Groupes et rôles"], dependencies=[Depends(get_current_user)])

Db = Annotated[AsyncSession, Depends(get_db)]
User = Annotated[RequestContext, Depends(get_current_user)]
SuperAdmin = Annotated[RequestContext, Depends(require_admin)]


def _error(code: int, name: str, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"code": name, "message": message})


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} introuvable")


async def _visible_group(repository: AccessGroupRepository, group_id: uuid.UUID, user: RequestContext) -> AppGroup:
    """404 pour un groupe dont on n'est pas membre : son existence ne se devine pas."""
    group = await repository.get_group(group_id)
    if group is None or not (user.is_admin or str(group.id) in user.groups):
        raise _not_found("Groupe")
    return group


async def _manager_of(
    repository: AccessGroupRepository, group_id: uuid.UUID, user: RequestContext
) -> tuple[AppGroup, set[Permission]]:
    group = await _visible_group(repository, group_id, user)
    mine = await repository.permissions_in(user, group.id)
    if Permission.GROUP_MEMBERS not in mine:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Vous ne gérez pas les membres de ce groupe.")
    return group, mine


async def _role_within(repository: AccessGroupRepository, role_id: uuid.UUID, mine: set[Permission]) -> AppRole:
    role = await repository.get_role(role_id)
    if role is None:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_role", "Ce rôle n'existe pas.")
    if not permissions_of(role) <= mine:
        raise _error(status.HTTP_403_FORBIDDEN, "role_too_wide", "Ce rôle donne plus de droits que le vôtre.")
    return role


async def _group_out(
    repository: AccessGroupRepository, group: AppGroup, user: RequestContext, count: int | None = None
) -> GroupOut:
    if count is None:
        count = (await repository.member_counts()).get(group.id, 0)
    mine = await repository.permissions_in(user, group.id)
    return GroupOut(
        id=group.id,
        name=group.name,
        description=group.description,
        member_count=count,
        can_manage_members=Permission.GROUP_MEMBERS in mine,
        can_create_analyses=Permission.ANALYSE_CREATE in mine,
        deletable=user.is_admin and not await repository.is_group_used(group.id),
        versions=[AccessVersionOut.model_validate(v) for v in group.versions] if user.is_admin else [],
    )


@groups_router.get("", response_model=list[GroupOut])
async def list_groups(db: Db, user: User) -> list[GroupOut]:
    """Les groupes de la personne ; tous pour un super admin."""
    repository = AccessGroupRepository(db)
    counts = await repository.member_counts()
    return [
        await _group_out(repository, group, user, counts.get(group.id, 0))
        for group in await repository.list_groups()
        if user.is_admin or str(group.id) in user.groups
    ]


@groups_router.get("/names", response_model=list[GroupName])
async def names(db: Db, ids: Annotated[list[str], Query(max_length=100)]) -> list[GroupName]:
    """Les noms de groupes dont on connaît déjà l'identifiant (accès d'un dossier, par exemple)."""
    return [GroupName(id=key, name=name) for key, name in (await group_names(db, ids)).items()]


@groups_router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
async def create_group(body: GroupIn, db: Db, user: SuperAdmin) -> GroupOut:
    repository = AccessGroupRepository(db)
    try:
        group = await repository.create_group(name=body.name, description=body.description, actor=user)
    except NameTakenError as error:
        raise _error(status.HTTP_409_CONFLICT, "name_taken", "Un groupe porte déjà ce nom.") from error
    return await _group_out(repository, group, user)


@groups_router.put("/{group_id}", response_model=GroupOut)
async def update_group(group_id: uuid.UUID, body: GroupIn, db: Db, user: SuperAdmin) -> GroupOut:
    repository = AccessGroupRepository(db)
    group = await _visible_group(repository, group_id, user)
    try:
        group = await repository.update_group(group, name=body.name, description=body.description, actor=user)
    except NameTakenError as error:
        raise _error(status.HTTP_409_CONFLICT, "name_taken", "Un groupe porte déjà ce nom.") from error
    return await _group_out(repository, group, user)


@groups_router.post("/{group_id}/restore/{version_id}", response_model=GroupOut)
async def restore_group(group_id: uuid.UUID, version_id: uuid.UUID, db: Db, user: SuperAdmin) -> GroupOut:
    repository = AccessGroupRepository(db)
    group = await _visible_group(repository, group_id, user)
    try:
        group = await repository.restore_group(group, version_id, user)
    except NameTakenError as error:
        raise _error(status.HTTP_409_CONFLICT, "name_taken", "Un groupe porte déjà ce nom.") from error
    if group is None:
        raise _not_found("Version")
    return await _group_out(repository, group, user)


@groups_router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: uuid.UUID, db: Db, user: SuperAdmin) -> Response:
    repository = AccessGroupRepository(db)
    group = await _visible_group(repository, group_id, user)
    try:
        await repository.delete_group(group, user)
    except InUseError as error:
        raise _error(
            status.HTTP_409_CONFLICT, "group_in_use", "Ce groupe a des membres, ou des dossiers ou outils s'y réfèrent."
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _member_out(
    repository: AccessGroupRepository, members: list[AppGroupMember], mine: set[Permission]
) -> list[MemberOut]:
    people = await repository.people({m.user_id for m in members if m.user_id})
    roles = {role.id: permissions_of(role) for role in await repository.list_roles()}
    manages = Permission.GROUP_MEMBERS in mine
    out = []
    for member in members:
        person = people.get(member.user_id)
        out.append(
            MemberOut(
                id=member.id,
                user_id=member.user_id,
                name=person.name if person else "",
                email=member.email or (person.email if person else ""),
                role_id=member.role_id,
                pending=member.user_id is None,
                editable=manages and roles[member.role_id] <= mine,
            )
        )
    return out


@groups_router.get("/{group_id}/members", response_model=list[MemberOut])
async def list_members(group_id: uuid.UUID, db: Db, user: User) -> list[MemberOut]:
    repository = AccessGroupRepository(db)
    group = await _visible_group(repository, group_id, user)
    mine = await repository.permissions_in(user, group.id)
    return await _member_out(repository, list(await repository.members(group.id)), mine)


@groups_router.post("/{group_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
async def add_member(group_id: uuid.UUID, body: MemberIn, db: Db, user: User) -> MemberOut:
    repository = AccessGroupRepository(db)
    group, mine = await _manager_of(repository, group_id, user)
    role = await _role_within(repository, body.role_id, mine)
    if body.user_id and body.user_id not in await repository.people([body.user_id]):
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_person", "Cette personne n'est pas connue.")
    try:
        member = await repository.add_member(group, role, actor=user, email=body.email, user_id=body.user_id)
    except AlreadyMemberError as error:
        raise _error(status.HTTP_409_CONFLICT, "already_member", "Cette personne est déjà membre du groupe.") from error
    return (await _member_out(repository, [member], mine))[0]


async def _editable_member(
    repository: AccessGroupRepository, group_id: uuid.UUID, member_id: uuid.UUID, user: RequestContext
) -> tuple[AppGroupMember, set[Permission]]:
    group, mine = await _manager_of(repository, group_id, user)
    member = await repository.get_member(group.id, member_id)
    if member is None:
        raise _not_found("Membre")
    await _role_within(repository, member.role_id, mine)
    return member, mine


@groups_router.patch("/{group_id}/members/{member_id}", response_model=MemberOut)
async def set_member_role(
    group_id: uuid.UUID, member_id: uuid.UUID, body: MemberRoleIn, db: Db, user: User
) -> MemberOut:
    repository = AccessGroupRepository(db)
    member, mine = await _editable_member(repository, group_id, member_id, user)
    role = await _role_within(repository, body.role_id, mine)
    member = await repository.set_member_role(member, role, user)
    return (await _member_out(repository, [member], mine))[0]


@groups_router.delete("/{group_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(group_id: uuid.UUID, member_id: uuid.UUID, db: Db, user: User) -> Response:
    repository = AccessGroupRepository(db)
    member, _ = await _editable_member(repository, group_id, member_id, user)
    await repository.remove_member(member, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@groups_router.get("/{group_id}/events", response_model=list[GroupEventOut])
async def group_events(group_id: uuid.UUID, db: Db, user: User) -> list[GroupEventOut]:
    repository = AccessGroupRepository(db)
    group, _ = await _manager_of(repository, group_id, user)
    events = await repository.events(group.id)
    people = await repository.people({e.subject_user_id for e in events if e.subject_user_id})
    return [
        GroupEventOut(
            id=e.id,
            type=e.type,
            created_at=e.created_at,
            actor_name=e.actor_name,
            subject=e.subject_email or (people[e.subject_user_id].name if e.subject_user_id in people else None),
            role_name=e.role_name,
            previous_role_name=e.previous_role_name,
        )
        for e in events
    ]


async def _role_out(
    repository: AccessGroupRepository, role: AppRole, user: RequestContext, mine: set[Permission]
) -> RoleOut:
    return RoleOut(
        id=role.id,
        name=role.name,
        description=role.description,
        permissions=sorted(permissions_of(role), key=list(Permission).index),
        system=role.system,
        in_use=await repository.is_role_used(role.id),
        assignable=permissions_of(role) <= mine,
        versions=[AccessVersionOut.model_validate(v) for v in role.versions] if user.is_admin else [],
    )


async def _existing_role(repository: AccessGroupRepository, role_id: uuid.UUID) -> AppRole:
    role = await repository.get_role(role_id)
    if role is None:
        raise _not_found("Rôle")
    return role


def _frozen() -> HTTPException:
    return _error(status.HTTP_409_CONFLICT, "system_role", "Ce rôle est fourni par l'application : il est figé.")


def _role_name_taken() -> HTTPException:
    return _error(status.HTTP_409_CONFLICT, "name_taken", "Un rôle porte déjà ce nom.")


@roles_router.get("", response_model=list[RoleOut])
async def list_roles(db: Db, user: User, group_id: uuid.UUID | None = None) -> list[RoleOut]:
    repository = AccessGroupRepository(db)
    mine = await repository.permissions_in(user, group_id) if group_id else set(Permission) if user.is_admin else set()
    return [await _role_out(repository, role, user, mine) for role in await repository.list_roles()]


@roles_router.post("", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
async def create_role(body: RoleIn, db: Db, user: SuperAdmin) -> RoleOut:
    repository = AccessGroupRepository(db)
    try:
        role = await repository.create_role(**body.model_dump(), actor=user)
    except NameTakenError as error:
        raise _role_name_taken() from error
    return await _role_out(repository, role, user, set(Permission))


@roles_router.put("/{role_id}", response_model=RoleOut)
async def update_role(role_id: uuid.UUID, body: RoleIn, db: Db, user: SuperAdmin) -> RoleOut:
    repository = AccessGroupRepository(db)
    role = await _existing_role(repository, role_id)
    try:
        role = await repository.update_role(role, **body.model_dump(), actor=user)
    except SystemRoleError as error:
        raise _frozen() from error
    except NameTakenError as error:
        raise _role_name_taken() from error
    return await _role_out(repository, role, user, set(Permission))


@roles_router.post("/{role_id}/restore/{version_id}", response_model=RoleOut)
async def restore_role(role_id: uuid.UUID, version_id: uuid.UUID, db: Db, user: SuperAdmin) -> RoleOut:
    repository = AccessGroupRepository(db)
    role = await _existing_role(repository, role_id)
    try:
        role = await repository.restore_role(role, version_id, user)
    except NameTakenError as error:
        raise _role_name_taken() from error
    if role is None:
        raise _not_found("Version")
    return await _role_out(repository, role, user, set(Permission))


@roles_router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(role_id: uuid.UUID, db: Db, user: SuperAdmin) -> Response:
    repository = AccessGroupRepository(db)
    role = await _existing_role(repository, role_id)
    try:
        await repository.delete_role(role)
    except SystemRoleError as error:
        raise _frozen() from error
    except InUseError as error:
        raise _error(status.HTTP_409_CONFLICT, "role_in_use", "Ce rôle est encore attribué.") from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
