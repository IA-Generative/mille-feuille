"""La fin d'une étape d'exécution et la reprise d'une synthèse d'agent : partagées par la route interne et par les
agents du backend."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dossier import DossierStatus, ExecutionStep
from app.repositories.dossier_analysis_repository import DossierAnalysisRepository
from app.repositories.dossier_repository import DossierRepository
from app.repositories.ephemeral_repository import EphemeralRepository
from app.services import analysis_builder, analysis_carryover
from app.services.ephemeral_run_service import finalize_run


async def complete_step(db: AsyncSession, step_id: uuid.UUID, status, output: str | None):  # noqa: ANN001, ANN201
    """Termine l'étape (terminée ou en échec) avec sa sortie. None si elle n'existe plus."""
    repository = DossierRepository(db)
    step = await repository.get_execution_step_by_id(step_id)
    if step is None:
        return None
    completed = await repository.complete_execution_step(step, status, output)
    # Analyse de dossier (#125) : n'empêche jamais l'étape de se terminer.
    await analysis_builder.record_step_result(step_id)
    # Pose du TTL dès que le Dossier vient de passer à un état terminal (cf.
    # docs/ephemeral-api.md) - no-op immédiat si ce n'est pas encore le cas
    # (mark_dossier_terminal vérifie ended_at) ou si le dossier n'est pas
    # éphémère.
    dossier = await repository.get(completed.dossier_id)
    if dossier is not None and dossier.status != DossierStatus.EN_COURS:
        await EphemeralRepository(db).mark_dossier_terminal(dossier)
        # Run éphémère persist=false : on garde le résultat, on supprime dossier et analyse.
        # `completed` est sérialisé après ; il a déjà été chargé (logs comprises) avant.
        await finalize_run(db, dossier.id)
    return completed


async def reusable_agent_output(db: AsyncSession, dossier_id: uuid.UUID, step_id: uuid.UUID) -> str | None:
    """La synthèse de l'analyse précédente, si l'agent de cette étape peut la reprendre : son empreinte (configuration
    et ce qu'il lit) est inchangée. None sinon."""
    analyses = DossierAnalysisRepository(db)
    analysis = await analyses.get_current(dossier_id)
    step = await db.get(ExecutionStep, step_id)
    if analysis is None or step is None or step.dossier_id != dossier_id:
        return None
    fingerprint = await analysis_builder.agent_fingerprint(analyses, analysis, step)
    if fingerprint is None:
        return None
    reused = await analysis_carryover.reuse_agent_unit(analyses, analysis, step, fingerprint)
    return reused[1] if reused is not None else None
