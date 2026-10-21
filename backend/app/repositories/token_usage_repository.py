import uuid
from datetime import datetime

from sqlalchemy import Date, String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_token import AppToken
from app.models.app_user import AppUser
from app.models.dossier_ephemere import DossierEphemere
from app.models.token_usage import TokenUsage


def _sums():
    return (
        func.coalesce(func.sum(TokenUsage.input_tokens), 0).label("input_tokens"),
        func.coalesce(func.sum(TokenUsage.output_tokens), 0).label("output_tokens"),
        func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("total_tokens"),
        func.count(TokenUsage.id).label("calls"),
    )


def _biggest_first():
    return func.sum(TokenUsage.total_tokens).desc()


class TokenUsageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(self, usage: TokenUsage) -> None:
        self.db.add(usage)

    async def ephemeral_creator(self, dossier_id: uuid.UUID) -> str | None:
        """Qui a lancé le run éphémère de ce dossier (personne, jeton API ou clé d'environnement), s'il en est un."""
        return await self.db.scalar(select(DossierEphemere.created_by).where(DossierEphemere.dossier_id == dossier_id))

    def _filtered(self, statement, since: datetime, user_id: str | None):
        statement = statement.where(TokenUsage.created_at >= since)
        return statement.where(TokenUsage.user_id == user_id) if user_id is not None else statement

    async def totals(self, since: datetime, user_id: str | None):
        return (await self.db.execute(self._filtered(select(*_sums()), since, user_id))).one()

    async def by_step(self, since: datetime, user_id: str | None):
        statement = select(TokenUsage.step, *_sums()).group_by(TokenUsage.step).order_by(_biggest_first())
        return (await self.db.execute(self._filtered(statement, since, user_id))).all()

    async def by_day(self, since: datetime, user_id: str | None):
        day = cast(TokenUsage.created_at, Date).label("day")
        statement = select(day, *_sums()).group_by(day).order_by(day)
        return (await self.db.execute(self._filtered(statement, since, user_id))).all()

    async def by_model(self, since: datetime, user_id: str | None):
        statement = select(TokenUsage.model, *_sums()).group_by(TokenUsage.model).order_by(_biggest_first())
        return (await self.db.execute(self._filtered(statement, since, user_id))).all()

    async def by_user(self, since: datetime):
        """Le nom vient de l'annuaire local (app_users) ou, pour un run éphémère lancé par un jeton API, du nom de ce
        jeton : jamais l'identifiant brut."""
        display = func.coalesce(AppUser.name, AppToken.name).label("display")
        statement = (
            select(TokenUsage.user_id, display, *_sums())
            .outerjoin(AppUser, AppUser.user_id == TokenUsage.user_id)
            .outerjoin(AppToken, cast(AppToken.id, String) == TokenUsage.user_id)
            .where(TokenUsage.created_at >= since)
            .group_by(TokenUsage.user_id, AppUser.name, AppToken.name)
            .order_by(_biggest_first())
        )
        return (await self.db.execute(statement)).all()
