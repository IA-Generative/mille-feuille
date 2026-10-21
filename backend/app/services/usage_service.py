import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.ephemeral import ENV_KEY_IDENTITY_ID
from app.core.security.factory import RequestContext
from app.models.token_usage import TokenUsage, TokenUsageKind
from app.repositories.token_usage_repository import TokenUsageRepository
from app.schemas.usage import DayUsage, ModelUsage, StepUsage, UsageIn, UsageOut, UsageSums, UserUsage

logger = logging.getLogger(__name__)


class NotAdminError(Exception):
    pass


def _sums(row) -> dict:  # noqa: ANN001
    return {
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "total_tokens": row.total_tokens,
        "calls": row.calls,
    }


def _display(row) -> str | None:  # noqa: ANN001
    if row.user_id == ENV_KEY_IDENTITY_ID:
        return "Clé d'API de l'environnement"
    return row.display


class UsageService:
    """Tokens consommés par les appels au LLM, par tâche, jour, modèle et personne."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.usage = TokenUsageRepository(db)

    async def record(self, entry: UsageIn) -> None:
        """Le run éphémère d'un dossier donne son auteur quand le worker n'en connaît pas : résolu ici, une fois, pour
        que la consommation reste attribuée après la purge du run."""
        user_id = entry.user_id
        if user_id is None and entry.dossier_id is not None:
            user_id = await self.usage.ephemeral_creator(entry.dossier_id)
        await self.usage.add(
            TokenUsage(
                user_id=user_id,
                step=entry.step,
                kind=entry.kind,
                model=entry.model,
                input_tokens=entry.input_tokens,
                output_tokens=entry.output_tokens,
                total_tokens=entry.input_tokens + entry.output_tokens,
                dossier_id=entry.dossier_id,
            )
        )
        await self.db.commit()

    async def record_quietly(
        self, step: str, model: str, input_tokens: int | None, output_tokens: int | None, user_id: str | None
    ) -> None:
        """Pour les appels du backend lui-même : le LLM a déjà répondu, un échec ici est journalisé, jamais
        remonté à l'utilisateur."""
        try:
            await self.record(
                UsageIn(
                    step=step,
                    model=model,
                    kind=TokenUsageKind.CHAT,
                    input_tokens=input_tokens or 0,
                    output_tokens=output_tokens or 0,
                    user_id=user_id,
                )
            )
        except Exception:
            logger.exception("Impossible d'enregistrer la consommation de tokens")
            await self.db.rollback()

    async def mine(self, user: RequestContext, days: int) -> UsageOut:
        return await self._report(days, user.user_id, with_users=False)

    async def overall(self, user: RequestContext, days: int, user_id: str | None = None) -> UsageOut:
        """La consommation de tout le monde, ou de `user_id` seulement. `by_user` liste toujours tout le monde, pour
        que l'administrateur puisse passer d'une personne à l'autre."""
        if not user.is_admin:
            raise NotAdminError(user.user_id)
        return await self._report(days, user_id, with_users=True)

    async def _report(self, days: int, user_id: str | None, with_users: bool) -> UsageOut:
        since = datetime.now(UTC) - timedelta(days=days)
        return UsageOut(
            days=days,
            totals=UsageSums(**_sums(await self.usage.totals(since, user_id))),
            by_step=[StepUsage(step=row.step, **_sums(row)) for row in await self.usage.by_step(since, user_id)],
            by_day=[DayUsage(day=row.day, **_sums(row)) for row in await self.usage.by_day(since, user_id)],
            by_model=[ModelUsage(model=row.model, **_sums(row)) for row in await self.usage.by_model(since, user_id)],
            by_user=[
                UserUsage(user_id=row.user_id, display=_display(row), **_sums(row))
                for row in await self.usage.by_user(since)
            ]
            if with_users
            else [],
        )
