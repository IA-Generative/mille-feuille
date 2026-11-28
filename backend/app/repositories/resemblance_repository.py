"""Thèmes de ressemblance (#649). Les droits sont appliqués **à la lecture**, jamais au calcul : un groupe n'est montré
que pour ses dossiers visibles de la personne, et seulement s'il en reste au moins deux."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, delete, distinct, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ResemblanceSettings
from app.core.security.factory import RequestContext
from app.models.analyse import Analyse, EntityDefinition
from app.models.dossier import Dossier
from app.models.resemblance import (
    ResemblanceDismissal,
    ResemblanceMember,
    ResemblanceTheme,
    ResemblanceThemeVersion,
)
from app.repositories.dossier_search_repository import DossierSearchRepository
from app.schemas.resemblance import (
    EntityOut,
    GroupOut,
    GroupPageOut,
    ThemeIn,
    ThemeOut,
    ThemeVersionOut,
)
from app.services import role_permissions
from app.services.dossier_access import visible_clause
from app.services.permissions import Permission
from app.services.resemblance.matching import find_groups


class UnknownEntityError(ValueError):
    pass


class GroupNotFoundError(LookupError):
    pass


class DismissalForbiddenError(PermissionError):
    pass


def _content(theme: ResemblanceTheme) -> dict:
    return {
        "name": theme.name,
        "description": theme.description,
        "scope": theme.scope,
        "certainty": theme.certainty,
        "active": theme.active,
        "criteria": theme.criteria,
    }


def _entity_ids(criteria: list[dict]) -> set[str]:
    return {i for criterion in criteria for i in criterion.get("entity_ids", [])}


def _dismissed() -> ColumnElement[bool]:
    return exists(
        select(ResemblanceDismissal.id).where(
            ResemblanceDismissal.theme_id == ResemblanceMember.theme_id,
            ResemblanceDismissal.group_key == ResemblanceMember.group_key,
            ResemblanceDismissal.restored_at.is_(None),
        )
    )


class ResemblanceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, theme_id: uuid.UUID) -> ResemblanceTheme | None:
        return await self.db.get(ResemblanceTheme, theme_id, populate_existing=True)

    # --- Thèmes ---

    async def list_for(self, user: RequestContext) -> list[ThemeOut]:
        statement = select(ResemblanceTheme).order_by(ResemblanceTheme.created_at, ResemblanceTheme.id)
        if not user.is_admin:
            statement = statement.where(ResemblanceTheme.active)
        themes = list(await self.db.scalars(statement))
        counts = await self._group_counts(user)
        known = await self._known_entities(themes) if user.is_admin else set()
        return [self.to_schema(theme, user, counts.get(theme.id, 0), known) for theme in themes]

    def to_schema(
        self, theme: ResemblanceTheme, user: RequestContext, group_count: int = 0, known: set[str] | None = None
    ) -> ThemeOut:
        admin = user.is_admin
        return ThemeOut(
            id=theme.id,
            computed_at=theme.computed_at,
            group_count=group_count,
            versions=[ThemeVersionOut(id=v.id, created_at=v.created_at, content=v.content) for v in theme.versions]
            if admin
            else [],
            missing_entity_ids=sorted(_entity_ids(theme.criteria) - known) if admin and known is not None else [],
            **_content(theme),
        )

    async def known_entities_of(self, theme: ResemblanceTheme) -> set[str]:
        return await self._known_entities([theme])

    async def _known_entities(self, themes: list[ResemblanceTheme]) -> set[str]:
        wanted = [uuid.UUID(i) for theme in themes for i in _entity_ids(theme.criteria)]
        if not wanted:
            return set()
        found = await self.db.scalars(select(EntityDefinition.id).where(EntityDefinition.id.in_(wanted)))
        return {str(i) for i in found}

    async def _check_entities(self, criteria: list[dict], already: set[str]) -> None:
        """Une entité ajoutée doit exister ; une entité déjà citée peut avoir quitté son analyse depuis."""
        added = _entity_ids(criteria) - already
        if not added:
            return
        found = await self.db.scalars(
            select(EntityDefinition.id).where(EntityDefinition.id.in_([uuid.UUID(i) for i in added]))
        )
        if added - {str(i) for i in found}:
            raise UnknownEntityError("Une entité citée n'existe dans aucune analyse.")

    async def create(self, body: ThemeIn, user: RequestContext) -> ResemblanceTheme:
        content = body.model_dump(mode="json")
        await self._check_entities(content["criteria"], set())
        theme = ResemblanceTheme(created_by=user.user_id, **content)
        self.db.add(theme)
        await self.db.commit()
        return await self.get(theme.id)

    async def update(self, theme: ResemblanceTheme, content: dict, user: RequestContext) -> ResemblanceTheme:
        """Garde l'état précédent dans l'historique et retire les groupes, devenus périmés."""
        await self._check_entities(
            content["criteria"],
            _entity_ids(theme.criteria) | {i for v in theme.versions for i in _entity_ids(v.content["criteria"])},
        )
        if content == _content(theme):
            return theme
        self.db.add(ResemblanceThemeVersion(theme_id=theme.id, content=_content(theme), created_by=user.user_id))
        for key, value in content.items():
            setattr(theme, key, value)
        theme.computed_at = None
        await self.db.execute(delete(ResemblanceMember).where(ResemblanceMember.theme_id == theme.id))
        await self.db.commit()
        return await self.get(theme.id)

    async def delete(self, theme: ResemblanceTheme) -> None:
        await self.db.delete(theme)
        await self.db.commit()

    # --- Groupes ---

    def _groups_of(self, user: RequestContext, *, dismissed: bool):
        """Les groupes d'au moins deux dossiers visibles : (thème, clé, nombre)."""
        state = _dismissed() if dismissed else ~_dismissed()
        return (
            select(
                ResemblanceMember.theme_id,
                ResemblanceMember.group_key,
                func.count(distinct(ResemblanceMember.dossier_id)).label("size"),
            )
            .join(Dossier, Dossier.id == ResemblanceMember.dossier_id)
            .join(ResemblanceTheme, ResemblanceTheme.id == ResemblanceMember.theme_id)
            .where(ResemblanceTheme.active, visible_clause(user), state)
            .group_by(ResemblanceMember.theme_id, ResemblanceMember.group_key)
            .having(func.count(distinct(ResemblanceMember.dossier_id)) > 1)
        )

    async def _group_counts(self, user: RequestContext) -> dict[uuid.UUID, int]:
        if not ResemblanceSettings().RESEMBLANCE_ENABLED:
            return {}
        groups = self._groups_of(user, dismissed=False).subquery()
        rows = await self.db.execute(select(groups.c.theme_id, func.count()).group_by(groups.c.theme_id))
        return dict(rows.all())

    async def groups(
        self, theme: ResemblanceTheme, user: RequestContext, *, page: int, page_size: int, dismissed: bool
    ) -> GroupPageOut:
        empty = GroupPageOut(items=[], total=0, page=page, page_size=page_size)
        if not theme.active or not ResemblanceSettings().RESEMBLANCE_ENABLED:
            return empty
        found = self._groups_of(user, dismissed=dismissed).where(ResemblanceMember.theme_id == theme.id).subquery()
        total = await self.db.scalar(select(func.count()).select_from(found)) or 0
        keys = list(
            await self.db.scalars(
                select(found.c.group_key)
                .order_by(found.c.size.desc(), found.c.group_key)
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        if not keys:
            return empty.model_copy(update={"total": total})

        members: dict[str, set[uuid.UUID]] = defaultdict(set)
        rows = await self.db.execute(
            select(ResemblanceMember.group_key, Dossier.id)
            .join(Dossier, Dossier.id == ResemblanceMember.dossier_id)
            .where(ResemblanceMember.theme_id == theme.id, ResemblanceMember.group_key.in_(keys), visible_clause(user))
        )
        for key, dossier_id in rows:
            members[key].add(dossier_id)
        # Les preuves sont relues sur les valeurs actuelles, des seuls dossiers visibles.
        ids = sorted({i for found_ids in members.values() for i in found_ids}, key=str)
        current = await find_groups(
            self.db, theme.criteria, theme.scope, where=[Dossier.id.in_(ids), visible_clause(user)]
        )

        search = DossierSearchRepository(self.db)
        described = {d.id: d for d in await search.describe(ids, {})}
        items = []
        for key in keys:
            group = current.get(key)
            kept = [i for i in group.dossiers if i in members[key]] if group else []
            if len(kept) < 2:
                continue
            items.append(
                GroupOut(
                    key=key,
                    label=" + ".join(group.labels),
                    reason=f"En commun : {' et '.join(c['name'].lower() for c in theme.criteria)}.",
                    certainty=theme.certainty,
                    dossiers=[described[i] for i in kept],
                    occurrences=[o for o in group.occurrences if o.dossier_id in kept],
                    dismissed=dismissed,
                )
            )
        await search.trace_admin_access(user, sorted({d.id for item in items for d in item.dossiers}, key=str))
        return GroupPageOut(items=items, total=total, page=page, page_size=page_size)

    async def set_dismissed(self, theme: ResemblanceTheme, key: str, user: RequestContext, *, dismissed: bool) -> None:
        """Écarte un groupe, pour tout le monde, ou le rétablit. Il faut en voir au moins deux dossiers et pouvoir
        valider sur chacun de ceux qu'on voit."""
        ids = list(
            await self.db.scalars(
                select(Dossier.id)
                .join(ResemblanceMember, ResemblanceMember.dossier_id == Dossier.id)
                .where(ResemblanceMember.theme_id == theme.id, ResemblanceMember.group_key == key, visible_clause(user))
            )
        )
        if len(ids) < 2:
            raise GroupNotFoundError
        for dossier_id in ids:
            if Permission.DOSSIER_VALIDATE not in await role_permissions.dossier_permissions(self.db, dossier_id, user):
                raise DismissalForbiddenError
        active = await self.db.scalar(
            select(ResemblanceDismissal).where(
                ResemblanceDismissal.theme_id == theme.id,
                ResemblanceDismissal.group_key == key,
                ResemblanceDismissal.restored_at.is_(None),
            )
        )
        if dismissed and active is None:
            name = f"{user.first_name} {user.last_name}".strip() or user.email
            self.db.add(
                ResemblanceDismissal(
                    theme_id=theme.id, group_key=key, dismissed_by=user.user_id, dismissed_by_name=name
                )
            )
        elif not dismissed and active is not None:
            active.restored_at, active.restored_by = datetime.now(UTC), user.user_id
        await self.db.commit()

    # --- Entités ---

    async def entities(self) -> list[EntityOut]:
        rows = await self.db.execute(
            select(EntityDefinition, Analyse.name)
            .join(Analyse, Analyse.id == EntityDefinition.analyse_id)
            .order_by(Analyse.name, Analyse.id, EntityDefinition.position)
        )
        return [
            EntityOut(
                id=entity.id,
                name=entity.name,
                definition=entity.definition,
                type=entity.type.value,
                analyse_name=analyse_name,
            )
            for entity, analyse_name in rows.unique()
        ]
