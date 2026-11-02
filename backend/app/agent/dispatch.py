"""Les entrées de l'agent : ce que les routeurs déposent pour qu'un travail soit mené en arrière-plan.

Les noms et les arguments sont ceux qu'avait `app.celery_client` pour le worker agent_execution : les routeurs (et
leurs tests) n'ont changé que d'import. Un dépôt rend la main aussitôt ; le travail tourne dans la boucle du backend
(voir runner.py)."""

import logging
from functools import partial

from sqlalchemy import select

from app.agent.jobs.document_fields import generate_document_fields
from app.agent.jobs.suggestion import suggest_dossier_analyse
from app.agent.jobs.summary import run_document_summary, run_dossier_summary
from app.agent.runner import IsAlive, agent_runner
from app.db import async_session_factory
from app.models.document_draft import DocumentDraft
from app.models.dossier import Dossier, DossierDocument, SuggestionStatus
from app.models.summary import SummaryStatus
from app.repositories.document_draft_repository import GENERATION_FAILED, GENERATION_RUNNING

logger = logging.getLogger(__name__)

_INTERRUPTED = "Le calcul a été interrompu : le serveur qui l'exécutait s'est arrêté."


def _document_summary_name(document_id: str) -> str:
    return f"document-summary-{document_id}"


def _dossier_summary_name(dossier_id: str) -> str:
    return f"dossier-summary-{dossier_id}"


def _suggestion_name(dossier_id: str) -> str:
    return f"analyse-suggestion-{dossier_id}"


def _generation_name(draft_id: str) -> str:
    return f"document-generation-{draft_id}"


def dispatch_document_summary(dossier_id: str, document_id: str) -> None:
    """Résumé d'un document (issue #52) : l'agent concatène ses pages, appelle le LLM et dépose le résumé."""
    agent_runner.start(_document_summary_name(document_id), partial(run_document_summary, dossier_id, document_id))


def dispatch_dossier_summary(dossier_id: str) -> None:
    """Résumé global d'un dossier (issue #52) : résumés des documents et synthèses des agents."""
    agent_runner.start(_dossier_summary_name(dossier_id), partial(run_dossier_summary, dossier_id))


def dispatch_analyse_suggestion(dossier_id: str) -> None:
    """Suggestions d'analyse pour un dossier « à ranger » (issue #54)."""
    agent_runner.start(_suggestion_name(dossier_id), partial(suggest_dossier_analyse, dossier_id))


def dispatch_document_generation(draft_id: str, names: list[str] | None, instruction: str | None) -> None:
    """Valeurs des champs d'un brouillon de document (issue #141)."""
    agent_runner.start(_generation_name(draft_id), partial(generate_document_fields, draft_id, names, instruction))


# --- Travaux interrompus : un redémarrage laisse des statuts « en cours » que personne ne finira ---


async def _fail_stale_summaries(is_alive: IsAlive) -> None:
    async with async_session_factory() as db:
        documents = (
            (await db.execute(select(DossierDocument).where(DossierDocument.summary_status == SummaryStatus.EN_COURS)))
            .scalars()
            .all()
        )
        for document in documents:
            if not await is_alive(_document_summary_name(str(document.id))):
                document.summary_status = SummaryStatus.ECHEC
                document.summary_error = _INTERRUPTED
        dossiers = (
            (await db.execute(select(Dossier).where(Dossier.summary_status == SummaryStatus.EN_COURS))).scalars().all()
        )
        for dossier in dossiers:
            if not await is_alive(_dossier_summary_name(str(dossier.id))):
                dossier.summary_status = SummaryStatus.ECHEC
                dossier.summary_error = _INTERRUPTED
        await db.commit()


async def _fail_stale_suggestions(is_alive: IsAlive) -> None:
    async with async_session_factory() as db:
        dossiers = (
            (await db.execute(select(Dossier).where(Dossier.suggestion_status == SuggestionStatus.EN_COURS)))
            .scalars()
            .all()
        )
        for dossier in dossiers:
            if not await is_alive(_suggestion_name(str(dossier.id))):
                dossier.suggestion_status = SuggestionStatus.ECHEC
                dossier.summary_error = _INTERRUPTED
        await db.commit()


async def _fail_stale_generations(is_alive: IsAlive) -> None:
    async with async_session_factory() as db:
        drafts = (
            (await db.execute(select(DocumentDraft).where(DocumentDraft.generation_status == GENERATION_RUNNING)))
            .scalars()
            .all()
        )
        for draft in drafts:
            if not await is_alive(_generation_name(str(draft.id))):
                draft.generation_status = GENERATION_FAILED
                draft.generation_error = _INTERRUPTED
        await db.commit()


for _sweep in (_fail_stale_summaries, _fail_stale_suggestions, _fail_stale_generations):
    agent_runner.register_sweep(_sweep)
