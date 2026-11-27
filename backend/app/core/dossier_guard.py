"""Garde d'accès aux dossiers (issue #177) : **une dépendance pour toutes les routes `/dossiers/{dossier_id}/…`**.

Elle est branchée au niveau du routeur : une route ajoutée plus tard sous un identifiant de dossier est protégée
sans y penser (un test parcourt toutes les routes et vérifie que c'est le cas). Elle répond **404** à une personne
qui ne voit pas le dossier, comme s'il n'existait pas, **avant** de valider le corps de la requête. Un
administrateur qui entre dans un dossier restreint sans en être membre est tracé dans le journal (issue #182)."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.repositories.dossier_access_repository import DossierAccessRepository
from app.repositories.dossier_event_repository import DossierEventRepository
from app.services import required_permission, role_permissions
from app.services.permissions import Permission

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Battements de cœur et verrous : des écritures techniques, pas des actions sur le contenu du dossier.
TECHNICAL_PATHS = ("/presence", "/lock")


def permission_denied(permission: Permission) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "permission_denied",
            "message": "Votre rôle ne permet pas cette action.",
            "permission": permission.value,
        },
    )


async def check_dossier_access(
    db: AsyncSession,
    dossier_id: uuid.UUID,
    user: RequestContext,
    *,
    method: str = "GET",
    write: bool = False,
    need: Permission | None = None,
) -> str:
    """404 si la personne ne voit pas le dossier, 403 si son rôle ne donne pas la permission `need` (#664) ; trace
    l'entrée d'un administrateur hors de ses groupes (#182). Partagé par la garde des routes et par les chemins qui
    agissent au nom d'une personne (agent assistant)."""
    standing = await DossierAccessRepository(db).standing(dossier_id, user)
    if standing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")
    if need is not None and need not in await role_permissions.dossier_permissions(db, dossier_id, user):
        raise permission_denied(need)
    if standing == "admin_only":
        await DossierEventRepository(db).record_admin_access(dossier_id, user, method, write=write)
    return standing


async def require_dossier_visible(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> None:
    raw = request.path_params.get("dossier_id")
    if raw is None:
        return
    try:
        dossier_id = uuid.UUID(str(raw))
    except ValueError:
        return  # identifiant mal formé : la route le refuse elle-même (422)

    path = request.url.path
    write = request.method in WRITE_METHODS and not any(token in path for token in TECHNICAL_PATHS)
    need = None
    if request.method in WRITE_METHODS:
        need = required_permission.for_dossier(request.method, path.split(f"/dossiers/{raw}", 1)[-1])
    standing = await check_dossier_access(db, dossier_id, user, method=request.method, write=write, need=need)
    request.state.admin_only = standing == "admin_only"
