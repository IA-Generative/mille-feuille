import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.celery_client import celery_client
from app.config import EphemeralSettings
from app.db import async_session_factory
from app.repositories.analyse_repository import AnalyseRepository
from app.repositories.dossier_repository import DossierRepository
from app.repositories.ephemeral_repository import EphemeralRepository

logger = logging.getLogger(__name__)

# Purge horaire : fréquence à ajuster si le TTL minimum réel observé
# descendait sous l'heure (voir docs/ephemeral-api.md - TTL par défaut 24h).
celery_client.conf.beat_schedule = {
    "purge-expired-ephemeral": {
        "task": "app.tasks.purge_expired_ephemeral",
        "schedule": 3600.0,
        "options": {"queue": "maintenance"},
    },
}


async def run_purge() -> dict[str, int]:
    """Supprime les ressources éphémères expirées (dossier_ephemere puis
    analyse_ephemere, dans cet ordre : une analyse encore référencée par un
    dossier_ephemere non supprimé n'est jamais purgée - même règle que le
    409 du DELETE manuel, cf. docs/ephemeral-api.md). Réutilise
    delete_dossier/delete (issues #21/#22) : même chemin de code qu'une
    suppression manuelle, S3 compris."""
    async with async_session_factory() as db:
        dossier_repository = DossierRepository(db)
        analyse_repository = AnalyseRepository(db)
        ephemeral_repository = EphemeralRepository(db)

        purged_dossiers = 0
        for dossier_ephemere in await ephemeral_repository.list_expired_dossier_ephemeres():
            dossier = await dossier_repository.get(dossier_ephemere.dossier_id)
            if dossier is not None:
                await dossier_repository.delete_dossier(dossier)
                purged_dossiers += 1

        purged_analyses = 0
        for analyse_ephemere in await ephemeral_repository.list_expired_analyse_ephemeres_without_runs():
            analyse = await analyse_repository.get(analyse_ephemere.analyse_id)
            if analyse is not None:
                await analyse_repository.delete(analyse)
                purged_analyses += 1

        purged_results = await ephemeral_repository.delete_expired_results()
        purged_metrics = 0
        retention_days = EphemeralSettings().EPHEMERAL_METRICS_RETENTION_DAYS
        if retention_days > 0:
            purged_metrics = await ephemeral_repository.delete_metrics_older_than(
                datetime.now(UTC) - timedelta(days=retention_days)
            )

        summary = {
            "purged_dossiers": purged_dossiers,
            "purged_analyses": purged_analyses,
            "purged_results": purged_results,
            "purged_metrics": purged_metrics,
        }
        logger.info("Purge éphémère : %s", summary)
        return summary


@celery_client.task(name="app.tasks.purge_expired_ephemeral")
def purge_expired_ephemeral() -> dict[str, int]:
    return asyncio.run(run_purge())
