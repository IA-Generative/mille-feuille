"""Le calcul des groupes d'un thème, en tâche de fond (#649). Rien n'est calculé tant qu'il n'est pas activé."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ResemblanceSettings
from app.db import async_session_factory
from app.models.dossier import Dossier
from app.models.resemblance import ResemblanceMember, ResemblanceTheme
from app.repositories.dossier_link_repository import common_limit
from app.services.resemblance.matching import find_groups

logger = logging.getLogger(__name__)


async def compute_theme(db: AsyncSession, theme_id: uuid.UUID) -> int:
    """Remplace les groupes du thème. Un thème désactivé, ou le calcul désactivé, n'en laisse aucun."""
    # Deux calculs du même thème (plusieurs instances) s'attendent.
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"resemblance:{theme_id}"))))
    theme = await db.get(ResemblanceTheme, theme_id)
    if theme is None:
        await db.rollback()
        return 0
    await db.execute(delete(ResemblanceMember).where(ResemblanceMember.theme_id == theme_id))
    rows = []
    if theme.active and ResemblanceSettings().RESEMBLANCE_ENABLED:
        limit = common_limit(await db.scalar(select(func.count()).select_from(Dossier)) or 0)
        for group in (await find_groups(db, theme.criteria, theme.scope)).values():
            # Ce que trop de dossiers partagent ne les rapproche pas.
            if len(group.dossiers) <= limit:
                rows += [{"theme_id": theme_id, "group_key": group.key, "dossier_id": d} for d in group.dossiers]
        theme.computed_at = datetime.now(UTC)
    if rows:
        await db.execute(insert(ResemblanceMember), rows)
    await db.commit()
    return len(rows)


async def run_theme(theme_id: str) -> None:
    async with async_session_factory() as db:
        try:
            await compute_theme(db, uuid.UUID(theme_id))
        except Exception as error:
            # Le message d'une erreur peut reprendre des valeurs extraites : on ne garde que son type.
            logger.error("Calcul du thème de ressemblance %s en échec : %s", theme_id, type(error).__name__)


async def run_all() -> None:
    async with async_session_factory() as db:
        ids = list(await db.scalars(select(ResemblanceTheme.id).where(ResemblanceTheme.active)))
    for theme_id in ids:
        await run_theme(str(theme_id))


async def periodic() -> None:
    """Suit les dossiers qui changent. Démarré avec l'application quand le calcul est activé."""
    while True:
        await run_all()
        await asyncio.sleep(max(1, ResemblanceSettings().RESEMBLANCE_INTERVAL_MINUTES) * 60)
