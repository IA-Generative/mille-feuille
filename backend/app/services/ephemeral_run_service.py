"""Fin de vie d'un run éphémère : on garde le résultat, on efface le reste.

Quand un run éphémère (persist=false) atteint un état terminal :
1. son résultat complet (ce que renvoie GET /api/ephemeral/runs/{id}) est copié dans
   `ephemeral_results`, avec l'`expires_at` calculé par le TTL du run ;
2. le Dossier est supprimé (documents, fichiers S3, captures, étapes, prédictions) ;
3. l'analyse éphémère persist=false est supprimée, si plus aucun dossier ne la référence.

La purge (app.tasks.purge_expired_ephemeral) supprime ensuite le résultat à `expires_at`.
Voir docs/ephemeral-api.md.
"""

import logging
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dossier import Dossier, DossierStatus
from app.models.dossier_ephemere import DossierEphemere
from app.repositories.analyse_repository import AnalyseRepository
from app.repositories.dossier_repository import DossierRepository
from app.repositories.ephemeral_repository import EphemeralRepository
from app.schemas.dossier import DossierOut
from app.schemas.ephemeral import EphemeralRunOut
from app.services.ephemeral_metrics import build_digest

logger = logging.getLogger(__name__)

_ACTIVE = (DossierStatus.EN_ATTENTE, DossierStatus.EN_COURS)


def to_run_schema(dossier: Dossier, record: DossierEphemere) -> EphemeralRunOut:
    return EphemeralRunOut(
        **DossierOut.model_validate(dossier).model_dump(),
        persist=record.persist,
        ttl_hours=record.ttl_hours,
        expires_at=record.expires_at,
    )


async def finalize_run(db: AsyncSession, dossier_id: uuid.UUID) -> bool:
    """Conserve le résultat du run puis supprime dossier et analyse éphémère.

    No-op (renvoie False) si le dossier n'est pas un run éphémère, si `persist=True`
    (tout est alors conservé), ou s'il n'est pas encore terminé. Idempotent : un
    second appel, une fois le dossier supprimé, ne fait rien.
    """
    ephemeral_repository = EphemeralRepository(db)
    record = await ephemeral_repository.get_dossier_ephemere(dossier_id)
    if record is None or record.persist:
        return False
    dossier_repository = DossierRepository(db)
    dossier = await dossier_repository.get(dossier_id)
    if dossier is None or dossier.status in _ACTIVE:
        return False

    await ephemeral_repository.mark_dossier_terminal(dossier)
    await db.refresh(record)
    if record.expires_at is None:  # dossier terminal sans ended_at : ne devrait pas arriver
        return False

    # Copiés avant la suppression : `record` disparaît avec le dossier.
    analyse_ephemere_id = record.analyse_ephemere_id
    created_by = record.created_by
    expires_at = record.expires_at
    payload = to_run_schema(dossier, record).model_dump(mode="json")
    # Captures de pages conservées avec le résultat (jusqu'à expires_at) : de quoi afficher les zones des entités.
    screenshot_keys = {
        str(page.id): page.screenshot_key
        for document in dossier.documents
        for page in document.pages
        if page.screenshot_key
    }
    # Sauvegardé AVANT toute suppression : si la suite échoue, le résultat n'est pas perdu.
    await ephemeral_repository.save_result(
        run_id=dossier_id,
        created_by=created_by,
        payload=payload,
        expires_at=expires_at,
        screenshot_keys=screenshot_keys,
    )
    # Le condensé non sensible survit à la purge du résultat (métriques et verdicts, voir EphemeralRunMetrics).
    await ephemeral_repository.save_run_metrics(
        run_id=dossier_id, created_by=created_by, digest=build_digest(to_run_schema(dossier, record))
    )
    # La ligne dossier_ephemere part avec le dossier (ondelete=CASCADE).
    await dossier_repository.delete_dossier(dossier, keep_screenshots=True)

    if analyse_ephemere_id is not None and await _delete_analyse_if_unused(db, analyse_ephemere_id):
        payload["analyse_id"] = None  # l'analyse n'existe plus : évite un identifiant orphelin
        await ephemeral_repository.save_result(
            run_id=dossier_id, created_by=created_by, payload=payload, expires_at=expires_at
        )
    return True


async def _delete_analyse_if_unused(db: AsyncSession, analyse_id: uuid.UUID) -> bool:
    """Supprime l'analyse éphémère persist=false ; pas si un autre run la référence encore
    (la FK Dossier.analyse_id est RESTRICT : le dernier run terminé la supprimera)."""
    ephemeral_repository = EphemeralRepository(db)
    analyse_ephemere = await ephemeral_repository.get_analyse_ephemere(analyse_id)
    if analyse_ephemere is None or analyse_ephemere.persist:
        return False
    analyse_repository = AnalyseRepository(db)
    analyse = await analyse_repository.get(analyse_id)
    if analyse is None:
        return False
    try:
        await analyse_repository.delete(analyse)
    except IntegrityError:
        await db.rollback()
        return False
    return True
