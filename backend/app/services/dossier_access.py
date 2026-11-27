"""Qui voit un dossier (issue #177). **Une seule règle**, partagée par les dépôts : aucune route ne réécrit la sienne.

- un **administrateur** voit tout ;
- un dossier **restreint** est vu des membres d'un groupe associé (pas d'héritage entre groupes) ;
- un dossier **« selon l'analyse »** est vu de qui a accès à son analyse (`services/analyse_access.py`) ;
- un dossier **« à ranger »** (sans analyse) n'a pas encore d'analyse dont hériter : il suit les groupes associés ;
- le **créateur** n'a aucun droit propre : son accès vient de ses groupes.
"""

from collections.abc import Collection
from typing import TYPE_CHECKING

from sqlalchemy import ColumnElement, and_, exists, false, or_, select, true

from app.models.dossier import Dossier
from app.models.dossier_access import DossierGroupAccess, Visibility
from app.services.analyse_access import membership_clause

if TYPE_CHECKING:
    from app.core.security.factory import RequestContext


def can_view(
    *,
    is_admin: bool,
    groups: Collection[str],
    visibility: str,
    has_analyse: bool,
    dossier_groups: Collection[str],
    has_analyse_access: bool,
) -> bool:
    """Règle d'accès en Python (une personne, un dossier). Doit rester équivalente à `visible_clause`."""
    if is_admin:
        return True
    if visibility == Visibility.ANALYSE.value and has_analyse:
        return has_analyse_access
    return bool(set(groups) & set(dossier_groups))


def visible_clause(user: "RequestContext") -> ColumnElement[bool]:
    """Condition SQL « ce dossier est visible de cette personne », à ajouter au `where` d'une requête sur `Dossier`."""
    if user.is_admin:
        return true()
    by_group = (
        exists(
            select(1).where(
                DossierGroupAccess.dossier_id == Dossier.id,
                DossierGroupAccess.group_id.in_(list(user.groups)),
            )
        )
        if user.groups
        else false()
    )
    by_analyse = and_(
        Dossier.visibility == Visibility.ANALYSE.value,
        Dossier.analyse_id.is_not(None),
        membership_clause(Dossier.analyse_id, user.user_id, user.groups),
    )
    # Un dossier « selon l'analyse » ne suit que son analyse, même s'il a eu des groupes.
    return or_(
        by_analyse,
        and_(or_(Dossier.visibility != Visibility.ANALYSE.value, Dossier.analyse_id.is_(None)), by_group),
    )
