from datetime import datetime

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_user import AppUser
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
        """Le nom vient de l'annuaire local (app_users), jamais l'identifiant Keycloak brut."""
        statement = (
            select(TokenUsage.user_id, AppUser.name.label("display"), *_sums())
            .outerjoin(AppUser, AppUser.user_id == TokenUsage.user_id)
            .where(TokenUsage.created_at >= since)
            .group_by(TokenUsage.user_id, AppUser.name)
            .order_by(_biggest_first())
        )
        return (await self.db.execute(statement)).all()
