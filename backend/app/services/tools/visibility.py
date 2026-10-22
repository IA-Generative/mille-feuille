"""Qui voit un serveur MCP. **Une seule règle**, en Python et en SQL (comme services/dossier_access.py) :

- un **administrateur** voit tout ;
- le **propriétaire** voit les siens ;
- un serveur « toute la plateforme » est vu de tous ;
- un serveur « mes groupes » est vu des membres d'un des groupes enregistrés à l'ajout ;
- un serveur privé n'est vu que de son propriétaire."""

from collections.abc import Collection

from sqlalchemy import ColumnElement, and_, false, or_, true
from sqlalchemy.dialects.postgresql import array

from app.models.tool import ToolServer, ToolVisibility


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


def visible_clause(user_id: str, is_admin: bool, groups: Collection[str]) -> ColumnElement[bool]:
    """Condition SQL « ce serveur est visible de cette personne » (à ajouter au `where` d'une requête `ToolServer`)."""
    if is_admin:
        return true()
    by_group = (
        and_(ToolServer.visibility == ToolVisibility.GROUPS, ToolServer.groups.has_any(array(list(groups))))
        if groups
        else false()
    )
    return or_(ToolServer.created_by == user_id, ToolServer.visibility == ToolVisibility.ALL, by_group)
