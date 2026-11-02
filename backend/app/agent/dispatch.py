"""Les entrées de l'agent : ce que les routeurs déposent pour qu'un travail soit mené en arrière-plan.

Les noms et les arguments sont ceux qu'avait `app.celery_client` pour le worker agent_execution : les routeurs (et
leurs tests) n'ont changé que d'import. Un dépôt rend la main aussitôt ; le travail tourne dans la boucle du backend
(voir runner.py).

Les travaux sont importés au moment du dépôt : ce module est importé par les repositories (suppression d'un dossier), et
les travaux importent les repositories."""

import logging
from functools import partial

from sqlalchemy import select

from app import celery_client
from app.agent.runner import IsAlive, agent_runner
from app.db import async_session_factory
from app.models.analyse import Agent
from app.models.document_draft import DocumentDraft
from app.models.dossier import (
    Dossier,
    DossierDocument,
    ExecutionStep,
    ExecutionStepKind,
    ExecutionStepStatus,
    SuggestionStatus,
)
from app.models.dossier_note import DossierNote
from app.models.question_answer import DossierQuestionAnswer, QuestionAnswerStatus
from app.models.search_index import DossierSearchIndex, IndexRebuild, IndexRebuildStatus, SearchIndexStatus
from app.models.summary import SummaryStatus
from app.repositories.document_draft_repository import GENERATION_FAILED, GENERATION_RUNNING
from app.repositories.dossier_note_repository import NOTE_ANALYSIS_FAILED, NOTE_ANALYSIS_RUNNING

logger = logging.getLogger(__name__)

_INTERRUPTED = "Le calcul a été interrompu : le serveur qui l'exécutait s'est arrêté."


def _question_answers_name(dossier_id: str) -> str:
    return f"question-answers-{dossier_id}"


def _agent_index_name(analyse_id: str) -> str:
    return f"index-agents-{analyse_id}"


def _document_summary_name(document_id: str) -> str:
    return f"document-summary-{document_id}"


def _dossier_summary_name(dossier_id: str) -> str:
    return f"dossier-summary-{dossier_id}"


def _suggestion_name(dossier_id: str) -> str:
    return f"analyse-suggestion-{dossier_id}"


def chat_job_name(conversation_id: str) -> str:
    return f"chat-{conversation_id}"


def _index_name(dossier_id: str, document_id: str) -> str:
    return f"index-document-{dossier_id}-{document_id}"


def _rebuild_name(rebuild_id: str) -> str:
    return f"index-rebuild-{rebuild_id}"


def _note_name(note_id: str) -> str:
    return f"note-proposals-{note_id}"


def _generation_name(draft_id: str) -> str:
    return f"document-generation-{draft_id}"


def dispatch_document_summary(dossier_id: str, document_id: str) -> None:
    """Résumé d'un document (issue #52) : l'agent concatène ses pages, appelle le LLM et dépose le résumé."""
    from app.agent.jobs.summary import run_document_summary

    agent_runner.start(_document_summary_name(document_id), partial(run_document_summary, dossier_id, document_id))


def dispatch_dossier_summary(dossier_id: str) -> None:
    """Résumé global d'un dossier (issue #52) : résumés des documents et synthèses des agents."""
    from app.agent.jobs.summary import run_dossier_summary

    agent_runner.start(_dossier_summary_name(dossier_id), partial(run_dossier_summary, dossier_id))


def dispatch_analyse_suggestion(dossier_id: str) -> None:
    """Suggestions d'analyse pour un dossier « à ranger » (issue #54)."""
    from app.agent.jobs.suggestion import suggest_dossier_analyse

    agent_runner.start(_suggestion_name(dossier_id), partial(suggest_dossier_analyse, dossier_id))


def dispatch_chat_response(conversation_id: str, dossier_id: str) -> None:
    """Réponse du chat du dossier à un message (ou à la décision de la personne sur un appel d'outil)."""
    from app.agent.chat.job import run_chat

    agent_runner.start(chat_job_name(conversation_id), partial(run_chat, conversation_id, dossier_id))


def dispatch_index_document(dossier_id: str, document_id: str) -> None:
    """Indexation des pages d'un document dans la recherche du dossier (découpage, embeddings, Qdrant)."""
    from app.services.search import indexing

    agent_runner.start(_index_name(dossier_id, document_id), partial(indexing.index_document, dossier_id, document_id))


def dispatch_rebuild_index(rebuild_id: str) -> None:
    """Reconstruction blue/green de l'index d'un dossier."""
    from app.services.search import indexing

    agent_runner.start(_rebuild_name(rebuild_id), partial(indexing.rebuild_index, rebuild_id))


def dispatch_finalize_rebuild(rebuild_id: str) -> None:
    from app.services.search import indexing

    agent_runner.start(f"index-finalize-{rebuild_id}", partial(indexing.finalize_rebuild, rebuild_id))


def dispatch_rollback_rebuild(rebuild_id: str) -> None:
    from app.services.search import indexing

    agent_runner.start(f"index-rollback-{rebuild_id}", partial(indexing.rollback_rebuild, rebuild_id))


def dispatch_drop_index(dossier_id: str) -> None:
    """Suppression de l'index d'un dossier supprimé."""
    from app.services.search import indexing

    agent_runner.start(f"index-drop-{dossier_id}", partial(indexing.drop_dossier_index, dossier_id))


def agents_job_name(dossier_id: str) -> str:
    return f"agents-{dossier_id}"


def dispatch_agent_execution(dossier_id: str, acting_user: str | None = None) -> None:
    """Exécution des agents d'une analyse sur un dossier. Ils attendent que la classification et l'extraction aient
    terminé. `acting_user` est la personne qui a lancé l'analyse : les agents appellent les serveurs MCP **en son nom**.
    Absente (exécution sans personne), ils n'ont accès qu'aux outils internes."""
    from app.agent.jobs.agents import run_agents

    agent_runner.start(agents_job_name(dossier_id), partial(run_agents, dossier_id, acting_user))


def dispatch_dossier_pipeline(document_ids: list[str], dossier_id: str) -> None:
    """Tout le pipeline d'un dossier : extraction de texte des documents, puis classification et extraction d'entités
    (chaîne Celery), et les agents, qui attendent la fin de ces deux étapes."""
    celery_client.dispatch_dossier_pipeline(document_ids, dossier_id)
    dispatch_agent_execution(dossier_id)


def dispatch_question_answers(dossier_id: str, full: bool = True) -> None:
    """Calcule les réponses aux questions fréquentes de l'analyse pour ce dossier (issue #422). `full` : fin d'une
    analyse (la liste de l'analyse fait foi) ; sinon une correction, qui ne rafraîchit que les réponses existantes."""
    from app.agent.jobs.question_answers import answer_questions

    agent_runner.start(_question_answers_name(dossier_id), partial(answer_questions, dossier_id, full))


def dispatch_index_agents(analyse_id: str) -> None:
    """Met à jour l'index des agents de l'analyse (le chat y retrouve l'agent qui répond à une question)."""
    from app.agent.jobs.agent_index import index_analyse_agents

    agent_runner.start(_agent_index_name(analyse_id), partial(index_analyse_agents, analyse_id))


def dispatch_helper_chat_response(conversation_id: str, model: str | None = None) -> None:
    """Réponse de l'assistant de l'application à un message de la personne (issue #50)."""
    from app.agent.helper.job import run_helper_chat

    agent_runner.start(f"helper-chat-{conversation_id}", partial(run_helper_chat, conversation_id, model))


def dispatch_note_proposals(note_id: str) -> None:
    """Propositions de mise à jour de l'analyse que justifie une note (issue #117)."""
    from app.agent.jobs.note_proposals import propose_from_note

    agent_runner.start(_note_name(note_id), partial(propose_from_note, note_id))


def dispatch_document_generation(draft_id: str, names: list[str] | None, instruction: str | None) -> None:
    """Valeurs des champs d'un brouillon de document (issue #141)."""
    from app.agent.jobs.document_fields import generate_document_fields

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


async def _fail_stale_note_analyses(is_alive: IsAlive) -> None:
    async with async_session_factory() as db:
        notes = (
            (await db.execute(select(DossierNote).where(DossierNote.analysis_status == NOTE_ANALYSIS_RUNNING)))
            .scalars()
            .all()
        )
        for note in notes:
            if not await is_alive(_note_name(str(note.id))):
                note.analysis_status = NOTE_ANALYSIS_FAILED
                note.analysis_error = _INTERRUPTED
        await db.commit()


async def _resume_stale_rebuilds(is_alive: IsAlive) -> None:
    """Une reconstruction ne refait que la différence : celle qu'un redémarrage a interrompue se relance."""
    async with async_session_factory() as db:
        rebuilds = (
            (await db.execute(select(IndexRebuild).where(IndexRebuild.status == IndexRebuildStatus.BUILDING)))
            .scalars()
            .all()
        )
        stale = [str(r.id) for r in rebuilds]
    for rebuild_id in stale:
        if not await is_alive(_rebuild_name(rebuild_id)):
            dispatch_rebuild_index(rebuild_id)


async def _fail_stale_indexing(is_alive: IsAlive) -> None:
    async with async_session_factory() as db:
        indexes = (
            (
                await db.execute(
                    select(DossierSearchIndex).where(DossierSearchIndex.status == SearchIndexStatus.INDEXING)
                )
            )
            .scalars()
            .all()
        )
        for index in indexes:
            dossier_id = str(index.dossier_id)
            if await agent_runner.is_alive_prefix(f"index-document-{dossier_id}-") or await agent_runner.is_alive(
                _rebuild_name(dossier_id)
            ):
                continue
            index.status = SearchIndexStatus.ERROR
            index.error = _INTERRUPTED
        await db.commit()


async def _fail_stale_agents(is_alive: IsAlive) -> None:
    """Les agents qu'un redémarrage a interrompus : l'étape passe en échec, le dossier peut se terminer."""
    from app.services.execution_steps import complete_step

    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(ExecutionStep.id, ExecutionStep.dossier_id).where(
                    ExecutionStep.kind == ExecutionStepKind.AGENT, ExecutionStep.status == ExecutionStepStatus.EN_COURS
                )
            )
        ).all()
    for step_id, dossier_id in rows:
        if not await is_alive(agents_job_name(str(dossier_id))):
            async with async_session_factory() as db:
                await complete_step(db, step_id, ExecutionStepStatus.ECHEC, _INTERRUPTED)


async def _fail_stale_question_answers(is_alive: IsAlive) -> None:
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(DossierQuestionAnswer).where(DossierQuestionAnswer.status == QuestionAnswerStatus.EN_COURS)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            if not await is_alive(_question_answers_name(str(row.dossier_id))):
                row.status = QuestionAnswerStatus.ECHEC
                row.error = _INTERRUPTED
                row.fingerprint = ""
        await db.commit()


async def _sync_agent_indexes(is_alive: IsAlive) -> None:
    """Au démarrage, les agents créés avant l'index (ou pendant une panne) sont indexés ; à jour, cela ne coûte rien."""
    from app.services.search import agent_index

    if not agent_index.configured():
        return
    async with async_session_factory() as db:
        analyse_ids = (await db.execute(select(Agent.analyse_id).distinct())).scalars().all()
    for analyse_id in analyse_ids:
        dispatch_index_agents(str(analyse_id))


for _sweep in (
    _sync_agent_indexes,
    _fail_stale_question_answers,
    _fail_stale_agents,
    _resume_stale_rebuilds,
    _fail_stale_indexing,
    _fail_stale_summaries,
    _fail_stale_suggestions,
    _fail_stale_generations,
    _fail_stale_note_analyses,
):
    agent_runner.register_sweep(_sweep)
