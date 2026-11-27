"""Accès à une analyse (issue #662).

Un super admin les modifie, comme qui a la permission « gérer les accès » dans un groupe de l'analyse. Celui-ci
n'associe ou ne retire que **ses** groupes, en laisse au moins un, et ne donne ni ne touche un rôle plus large que le
sien."""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analyse_guard import require_analyse_visible
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.repositories.access_group_repository import AccessGroupRepository, permissions_of
from app.repositories.analyse_access_repository import AnalyseAccessRepository, WantedPerson
from app.schemas.access_group import GroupName
from app.schemas.analyse_access import (
    AccessGroupOut,
    AccessPersonOut,
    AccessVersionSummary,
    AnalyseAccessIn,
    AnalyseAccessOut,
)
from app.services.analyse_access import groups_allowing
from app.services.group_names import group_names
from app.services.permissions import Permission

router = APIRouter(
    prefix="/analyses",
    tags=["Analyses"],
    dependencies=[Depends(get_current_user), Depends(require_analyse_visible)],
)

Db = Annotated[AsyncSession, Depends(get_db)]
User = Annotated[RequestContext, Depends(get_current_user)]


@dataclass
class _Rights:
    can_edit: bool
    # Les groupes que la personne peut associer ou retirer (aucune limite pour un super admin).
    groups: set[str]
    permissions: set[Permission]


async def _rights(db: AsyncSession, analyse_id: uuid.UUID, user: RequestContext) -> _Rights:
    if user.is_admin:
        return _Rights(True, set(), set(Permission))
    mine = set(await groups_allowing(db, user, Permission.ANALYSE_ACCESS))
    managing = mine & set(await AnalyseAccessRepository(db).group_ids(analyse_id))
    permissions: set[Permission] = set()
    repository = AccessGroupRepository(db)
    for group_id in managing:
        permissions |= await repository.permissions_in(user, uuid.UUID(group_id))
    return _Rights(bool(managing), mine, permissions)


async def _out(db: AsyncSession, analyse_id: uuid.UUID, user: RequestContext) -> AnalyseAccessOut:
    repository = AnalyseAccessRepository(db)
    rights = await _rights(db, analyse_id, user)
    roles = await repository.roles()
    group_ids = await repository.group_ids(analyse_id)
    people = await repository.people(analyse_id)
    versions = await repository.versions(analyse_id) if rights.can_edit else []
    parsed = [(version, *repository.read_version(version)) for version in versions]

    if user.is_admin:
        available = [str(group.id) for group in await AccessGroupRepository(db).list_groups()]
    else:
        available = sorted(rights.groups)
    known_ids = {p.user_id for p in people if p.user_id}
    known_ids |= {p.user_id for _, _, old in parsed for p in old if p.user_id}
    known = await AccessGroupRepository(db).people(known_ids)
    names = await group_names(db, set(group_ids) | set(available) | {g for _, old, _ in parsed for g in old})

    def label(user_id: str | None, email: str | None, role_id: uuid.UUID) -> str:
        who = known[user_id].name if user_id in known else email or "une personne"
        return f"{who} ({roles[role_id].name})" if role_id in roles else who

    return AnalyseAccessOut(
        can_edit=rights.can_edit,
        groups=[
            AccessGroupOut(
                id=g, name=names.get(g, g), editable=rights.can_edit and (user.is_admin or g in rights.groups)
            )
            for g in group_ids
        ],
        available_groups=[GroupName(id=g, name=names.get(g, g)) for g in available] if rights.can_edit else [],
        people=[
            AccessPersonOut(
                id=p.id,
                name=known[p.user_id].name if p.user_id in known else "",
                email=(p.email or (known[p.user_id].email if p.user_id in known else "")) if rights.can_edit else "",
                role_id=p.role_id,
                pending=p.user_id is None,
                editable=rights.can_edit and permissions_of(roles[p.role_id]) <= rights.permissions,
            )
            for p in people
        ],
        assignable_role_ids=[
            r.id for r in roles.values() if rights.can_edit and permissions_of(r) <= rights.permissions
        ],
        versions=[
            AccessVersionSummary(
                id=version.id,
                created_at=version.created_at,
                groups=[names.get(g, g) for g in old_groups],
                people=[label(p.user_id, p.email, p.role_id) for p in old_people],
            )
            for version, old_groups, old_people in parsed
        ],
    )


def _refused(code: int, name: str, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"code": name, "message": message})


async def _apply(
    db: AsyncSession, analyse_id: uuid.UUID, user: RequestContext, group_ids: list[str], people: list[WantedPerson]
) -> None:
    """Vérifie qu'on a le droit de passer de l'état actuel à celui-ci, puis l'écrit."""
    repository = AnalyseAccessRepository(db)
    rights = await _rights(db, analyse_id, user)
    if not rights.can_edit:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Vous ne gérez pas les accès de l'analyse.")
    roles = await repository.roles()
    if any(p.role_id not in roles for p in people):
        raise _refused(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_role", "Ce rôle n'existe pas.")
    wanted_groups = set(group_ids)
    current_groups = set(await repository.group_ids(analyse_id))
    if added_unknown := wanted_groups - current_groups - set(await group_names(db, wanted_groups)):
        if user.is_admin:
            raise _refused(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_group", f"Groupe inconnu : {sorted(added_unknown)[0]}"
            )
    if not user.is_admin:
        if (wanted_groups ^ current_groups) - rights.groups:
            raise _refused(status.HTTP_403_FORBIDDEN, "group_not_yours", "Vous ne changez que vos propres groupes.")
        if not wanted_groups:
            raise _refused(status.HTTP_422_UNPROCESSABLE_CONTENT, "groups_required", "Gardez au moins un groupe.")
        before = {(p.user_id, p.email, p.role_id) for p in await repository.people(analyse_id)}
        after = {(p.user_id, p.email, p.role_id) for p in people}
        if any(not permissions_of(roles[role_id]) <= rights.permissions for _, _, role_id in before ^ after):
            raise _refused(status.HTTP_403_FORBIDDEN, "role_too_wide", "Ce rôle donne plus de droits que le vôtre.")
    await repository.replace(analyse_id, group_ids, people, user.user_id)


@router.get("/{analyse_id}/access", response_model=AnalyseAccessOut)
async def get_access(analyse_id: uuid.UUID, db: Db, user: User) -> AnalyseAccessOut:
    return await _out(db, analyse_id, user)


@router.put("/{analyse_id}/access", response_model=AnalyseAccessOut)
async def set_access(analyse_id: uuid.UUID, body: AnalyseAccessIn, db: Db, user: User) -> AnalyseAccessOut:
    existing = {p.id: p for p in await AnalyseAccessRepository(db).people(analyse_id)}
    known = await AccessGroupRepository(db).people({p.user_id for p in body.people if p.user_id})
    people: list[WantedPerson] = []
    for person in body.people:
        if person.id is not None:
            if person.id not in existing:
                raise _refused(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_person", "Personne non ajoutée.")
            kept = existing[person.id]
            people.append(WantedPerson(person.role_id, kept.user_id, kept.email))
        elif person.user_id is not None:
            if person.user_id not in known:
                raise _refused(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_person", "Personne inconnue.")
            people.append(WantedPerson(person.role_id, person.user_id, None))
        else:
            people.append(WantedPerson(person.role_id, None, person.email.lower()))
    await _apply(db, analyse_id, user, body.group_ids, people)
    return await _out(db, analyse_id, user)


@router.post("/{analyse_id}/access/restore/{version_id}", response_model=AnalyseAccessOut)
async def restore_access(analyse_id: uuid.UUID, version_id: uuid.UUID, db: Db, user: User) -> AnalyseAccessOut:
    repository = AnalyseAccessRepository(db)
    version = next((v for v in await repository.versions(analyse_id) if v.id == version_id), None)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version introuvable")
    group_ids, people = repository.read_version(version)
    # Un groupe ou un rôle supprimé depuis n'est pas ressuscité.
    names = await group_names(db, group_ids)
    current = set(await repository.group_ids(analyse_id))
    roles = await repository.roles()
    await _apply(
        db,
        analyse_id,
        user,
        [g for g in group_ids if g in names or g in current],
        [p for p in people if p.role_id in roles],
    )
    return await _out(db, analyse_id, user)
