import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analyse import Analyse
from app.models.analyse_theme import AnalyseTheme, AnalyseThemeVersion
from app.repositories.analyse_repository import analyse_search_filters
from app.schemas.analyse import Version
from app.schemas.analyse_theme import AnalyseThemeOut


class ThemeNameTakenError(Exception):
    """Un autre thème porte déjà ce nom."""


class AnalyseThemeRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(self) -> Sequence[AnalyseTheme]:
        query = select(AnalyseTheme).order_by(AnalyseTheme.created_at, AnalyseTheme.id)
        return (await self.db.execute(query.execution_options(populate_existing=True))).scalars().all()

    async def get(self, theme_id: uuid.UUID) -> AnalyseTheme | None:
        return await self.db.get(AnalyseTheme, theme_id, populate_existing=True)

    async def analyse_counts(self, q: str | None = None) -> dict[uuid.UUID | None, int]:
        """Nombre d'analyses par thème (clé None : sans thème), limité à la recherche s'il y en a une."""
        query = select(Analyse.theme_id, func.count()).where(*analyse_search_filters(q)).group_by(Analyse.theme_id)
        return {theme_id: count for theme_id, count in await self.db.execute(query)}

    async def create(self, *, name: str, description: str, created_by: str | None) -> AnalyseTheme:
        theme = AnalyseTheme(name=name, description=description, created_by=created_by)
        self.db.add(theme)
        await self._commit_name()
        return await self.get(theme.id)

    async def update(self, theme: AnalyseTheme, *, name: str, description: str) -> AnalyseTheme:
        """Remplace le nom et la description ; l'ancienne valeur de chacun de ceux qui changent est conservée."""
        for field, value in (("name", name), ("description", description)):
            previous = getattr(theme, field)
            if value != previous:
                theme.versions.append(AnalyseThemeVersion(field=field, content=previous))
                setattr(theme, field, value)
        await self._commit_name()
        return await self.get(theme.id)

    async def delete(self, theme: AnalyseTheme) -> None:
        """Les analyses du thème sont conservées : la base les repasse « sans thème »."""
        await self.db.delete(theme)
        await self.db.commit()

    async def _commit_name(self) -> None:
        try:
            await self.db.commit()
        except IntegrityError as error:
            await self.db.rollback()
            raise ThemeNameTakenError from error

    @staticmethod
    def to_schema(theme: AnalyseTheme, analyse_count: int) -> AnalyseThemeOut:
        def versions(field: str) -> list[Version[str]]:
            return [
                Version(id=v.id, content=v.content, created_at=v.created_at) for v in theme.versions if v.field == field
            ]

        return AnalyseThemeOut(
            id=theme.id,
            name=theme.name,
            description=theme.description,
            analyse_count=analyse_count,
            name_versions=versions("name"),
            description_versions=versions("description"),
        )
