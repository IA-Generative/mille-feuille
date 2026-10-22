"""Qui voit un serveur MCP (et une source de connaissances, même règle). **Une seule règle**, en Python et en SQL
(comme services/dossier_access.py) :

- un **administrateur** voit tout ;
- le **propriétaire** voit les siens ;
- un serveur « toute la plateforme » est vu de tous ;
- un serveur « mes groupes » est vu des membres d'un des groupes enregistrés à l'ajout ;
- un serveur privé n'est vu que de son propriétaire."""

from collections.abc import Collection
from typing import TYPE_CHECKING

from sqlalchemy import ColumnElement, and_, false, or_, true
from sqlalchemy.dialects.postgresql import array

from app.models.knowledge_source import KnowledgeSource
from app.models.tool import ToolServer, ToolVisibility

if TYPE_CHECKING:
    from app.core.security.factory import RequestContext


def can_view(
    *,
    user_id: str,
    is_admin: bool,
    groups: Collection[str],
    owner_id: str,
    visibility: ToolVisibility,
    server_groups: Collection[str],
) -> bool:
    """Règle en Python. Doit rester équivalente à `visible_clause`."""
    if is_admin or owner_id == user_id or visibility == ToolVisibility.ALL:
        return True
    return visibility == ToolVisibility.GROUPS and bool(set(groups) & set(server_groups))


def visible_clause(
    user_id: str, is_admin: bool, groups: Collection[str], model: type[ToolServer] | type[KnowledgeSource] = ToolServer
) -> ColumnElement[bool]:
    """Condition SQL « ce serveur est visible de cette personne » (à ajouter au `where` d'une requête sur `model` :
    `ToolServer`, ou `KnowledgeSource` qui a les mêmes colonnes de propriétaire et de visibilité)."""
    if is_admin:
        return true()
    by_group = (
        and_(model.visibility == ToolVisibility.GROUPS, model.groups.has_any(array(list(groups))))
        if groups
        else false()
    )
    return or_(model.created_by == user_id, model.visibility == ToolVisibility.ALL, by_group)


def can_view_server(user: "RequestContext", server: ToolServer | KnowledgeSource) -> bool:
    """La même règle, pour une personne et un serveur (ou une source) chargés."""
    return can_view(
        user_id=user.user_id,
        is_admin=user.is_admin,
        groups=user.groups,
        owner_id=server.created_by,
        visibility=server.visibility,
        server_groups=server.groups,
    )
