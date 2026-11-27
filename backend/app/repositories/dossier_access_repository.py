import uuid
from collections.abc import Collection, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_user import AppUser
from app.models.dossier import Dossier
from app.models.dossier_access import DossierGroupAccess, Visibility
from app.models.dossier_event import DossierEventType
from app.repositories.dossier_event_repository import DossierEventRepository
from app.services.dossier_access import can_view
from app.services.group_names import group_labels


class DossierAccessRepository:
    """Groupes associés à un dossier et visibilité (issue #177). Les changements sont tracés dans le journal."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.events = DossierEventRepository(db)

    async def groups_of(self, dossier_id: uuid.UUID) -> Sequence[DossierGroupAccess]:
        result = await self.db.execute(
            select(DossierGroupAccess)
            .where(DossierGroupAccess.dossier_id == dossier_id)
            .order_by(DossierGroupAccess.keycloak_group)
        )
        return result.scalars().all()

    async def group_paths(self, dossier_id: uuid.UUID) -> list[str]:
        return [row.keycloak_group for row in await self.groups_of(dossier_id)]

    async def standing(self, dossier_id: uuid.UUID, user) -> str | None:
        """Position de la personne face au dossier : ``member`` (elle y a accès par la règle ordinaire),
        ``admin_only`` (elle n'y entre que parce qu'elle est administrateur : accès à tracer, #182), ou ``None``
        (dossier introuvable ou invisible)."""
        row = (
            await self.db.execute(select(Dossier.visibility, Dossier.analyse_id).where(Dossier.id == dossier_id))
        ).first()
        if row is None:
            return None
        visibility, analyse_id = row
        groups = await self.group_paths(dossier_id)
        if can_view(
            is_admin=False,
            groups=user.groups,
            visibility=visibility,
            has_analyse=analyse_id is not None,
            dossier_groups=groups,
        ):
            return "member"
        return "admin_only" if user.is_admin else None

    async def person_can_view(self, person: AppUser, dossier: Dossier) -> bool:
        """La personne (telle que l'annuaire l'a vue à sa dernière connexion) a-t-elle accès au dossier ?"""
        return can_view(
            is_admin=person.is_admin,
            groups=person.groups,
            visibility=dossier.visibility,
            has_analyse=dossier.analyse_id is not None,
            dossier_groups=await self.group_paths(dossier.id),
        )

    def add_groups(self, dossier_id: uuid.UUID, paths: Collection[str], granted_by: str | None) -> None:
        """Associe des groupes **sans valider** (dans la transaction de l'appelant)."""
        for path in sorted(set(paths)):
            self.db.add(DossierGroupAccess(dossier_id=dossier_id, keycloak_group=path, granted_by=granted_by))

    async def update(
        self,
        dossier: Dossier,
        *,
        visibility: Visibility,
        group_paths: Collection[str],
        actor,
        granted_by: str,
        commit: bool = True,
    ) -> dict:
        """Remplace la visibilité et les groupes du dossier, trace le changement et **annule l'affectation** d'une
        personne qui perd ainsi l'accès (tracée aussi). Renvoie le résumé du changement ; si une personne a été
        désaffectée, ``unassigned_person`` la nomme. ``commit=False`` laisse la transaction à l'appelant (lot,
        simulation)."""
        current = set(await self.group_paths(dossier.id))
        wanted = set(group_paths)
        added, removed = sorted(wanted - current), sorted(current - wanted)
        previous_visibility = dossier.visibility

        change: dict = {}
        if previous_visibility != visibility.value:
            change["visibility"] = {"from": previous_visibility, "to": visibility.value}
        if added:
            change["groups_added"] = added
        if removed:
            change["groups_removed"] = removed
        if not change:
            return {}

        dossier.visibility = visibility.value
        if removed:
            await self.db.execute(
                delete(DossierGroupAccess).where(
                    DossierGroupAccess.dossier_id == dossier.id, DossierGroupAccess.keycloak_group.in_(removed)
                )
            )
        self.add_groups(dossier.id, added, granted_by)
        await self.db.flush()
        # Le journal garde les noms du moment : lisibles même si un groupe est renommé ou supprimé.
        journal = dict(change)
        for key in ("groups_added", "groups_removed"):
            if key in journal:
                journal[key] = await group_labels(self.db, journal[key])
        self.events.add(dossier.id, DossierEventType.ACCESS_CHANGED, actor, journal)

        assignee = dossier.assignee
        if assignee is not None and not await self.person_can_view(assignee, dossier):
            # Imports tardifs : le dépôt des dossiers dépend de celui-ci (filtre de visibilité).
            from app.repositories.dossier_repository import DossierRepository

            DossierRepository(self.db)._apply_assignee(dossier, None, actor, reason="access_lost")
            change["assignee_unassigned"] = True
            change["unassigned_person"] = {"id": assignee.user_id, "name": assignee.name}
        if commit:
            await self.db.commit()
        return change
