import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import array, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import email_index
from app.models.analyse_access import AnalyseGroup, AnalysePerson
from app.models.app_user import AppUser
from app.models.dossier_access import Visibility
from app.utils.sorting import sort_key

if TYPE_CHECKING:
    from app.core.security.factory import RequestContext


def display_name(user: "RequestContext") -> str:
    return f"{user.first_name} {user.last_name}".strip() or user.email or user.user_id


class UserDirectoryRepository:
    """Annuaire local (issue #173) : qui peut recevoir un dossier. Alimenté à la connexion, jamais à la main."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def touch(self, user: "RequestContext") -> None:
        """Enregistre ou met à jour la personne connectée (nom, e-mail, groupes, rôle, dernière connexion)."""
        statement = insert(AppUser).values(
            user_id=user.user_id,
            name=display_name(user),
            email=user.email or "",
            email_index=email_index(user.email) if user.email else None,
            groups=list(user.groups),
            is_admin=user.is_admin,
        )
        await self.db.execute(
            statement.on_conflict_do_update(
                index_elements=[AppUser.user_id],
                set_={
                    "name": statement.excluded.name,
                    "email": statement.excluded.email,
                    "email_index": statement.excluded.email_index,
                    "groups": statement.excluded.groups,
                    "is_admin": statement.excluded.is_admin,
                    "last_seen_at": func.now(),
                },
            )
        )
        await self.db.commit()

    async def get(self, user_id: str) -> AppUser | None:
        return await self.db.get(AppUser, user_id)

    async def search(
        self, query: str | None, limit: int, *, entitled_to: tuple[str, uuid.UUID | None, Sequence[str]] | None = None
    ) -> Sequence[AppUser]:
        """Personnes connues, par nom ; ``query`` filtre sur le nom ou l'e-mail (sans casse). ``entitled_to`` =
        (visibilité, analyse, groupes du dossier) : ne garde que les personnes qui ont accès au dossier, selon
        l'annuaire (issue #177) ; même règle que `can_view`."""
        statement = select(AppUser)
        if entitled_to is not None:
            visibility, analyse_id, dossier_groups = entitled_to
            if visibility == Visibility.ANALYSE.value and analyse_id is not None:
                analyse_groups = (
                    await self.db.scalars(select(AnalyseGroup.group_id).where(AnalyseGroup.analyse_id == analyse_id))
                ).all()
                added = select(AnalysePerson.user_id).where(
                    AnalysePerson.analyse_id == analyse_id, AnalysePerson.user_id.is_not(None)
                )
                allowed = [AppUser.is_admin.is_(True), AppUser.user_id.in_(added)]
            else:
                analyse_groups = dossier_groups
                allowed = [AppUser.is_admin.is_(True)]
            if analyse_groups:
                allowed.append(AppUser.groups.has_any(array(list(analyse_groups))))
            statement = statement.where(or_(*allowed))
        people = (await self.db.execute(statement)).scalars().all()
        # Nom et e-mail sont chiffrés en base : recherche et tri se font ici, l'annuaire restant de taille modeste.
        if query and query.strip():
            wanted = query.strip().casefold()
            people = [p for p in people if wanted in p.name.casefold() or wanted in p.email.casefold()]
        return sorted(people, key=lambda p: (sort_key(p.name), p.user_id))[:limit]
