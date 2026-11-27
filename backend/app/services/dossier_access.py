"""Qui voit un dossier (issue #177). **Une seule règle**, partagée par les dépôts : aucune route ne réécrit la sienne.

- un **administrateur** voit tout ;
- un dossier **restreint** est vu des membres d'un groupe associé (chemin exact, sans héritage) ;
- un dossier **« selon l'analyse »** est vu de tout utilisateur qui a accès à son analyse (aujourd'hui : toute
  personne connectée) ;
- un dossier **« à ranger »** (sans analyse) n'a pas encore d'analyse dont hériter : il suit les groupes associés ;
- le **créateur** n'a aucun droit propre : son accès vient de ses groupes.
"""

from collections.abc import Collection

from sqlalchemy import ColumnElement, and_, exists, false, or_, select, true

from app.models.dossier import Dossier
from app.models.dossier_access import DossierGroupAccess, Visibility


def can_view(
    *,
    is_admin: bool,
    groups: Collection[str],
    visibility: str,
    has_analyse: bool,
    dossier_groups: Collection[str],
) -> bool:
    """Règle d'accès en Python (une personne, un dossier). Doit rester équivalente à `visible_clause`."""
    if is_admin:
        return True
    if visibility == Visibility.ANALYSE.value and has_analyse:
        return True
    return bool(set(groups) & set(dossier_groups))


def visible_clause(is_admin: bool, groups: Collection[str]) -> ColumnElement[bool]:
    """Condition SQL « ce dossier est visible de cette personne », à ajouter au `where` d'une requête sur `Dossier`."""
    if is_admin:
        return true()
    by_group = (
        exists(
            select(1).where(
                DossierGroupAccess.dossier_id == Dossier.id,
                DossierGroupAccess.group_id.in_(list(groups)),
            )
        )
        if groups
        else false()
    )
    return or_(and_(Dossier.visibility == Visibility.ANALYSE.value, Dossier.analyse_id.is_not(None)), by_group)
