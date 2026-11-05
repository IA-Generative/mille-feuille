"""Exécution des agents d'une analyse sur un dossier.

Les agents attendent que la classification et l'extraction (d'autres travaux, menés par leurs propres workers) aient
terminé : ils lisent leurs prédictions. Chaque agent a une étape d'exécution, qui reçoit sa synthèse (ou son échec) ;
quand tous ont fini, le résumé global du dossier est lancé. Chaque agent reçoit :
- son prompt (défini dans l'analyse) ;
- un socle d'outils (recherche dans le dossier, lecture de page, classifications, entités) ;
- les outils choisis pour lui : calculatrice, dates, serveurs MCP — appelés au nom de la personne qui a lancé
  l'analyse —, base de connaissances ;
- le modèle LLM configuré pour lui (ou le modèle par défaut)."""

import asyncio
import logging
import time
import uuid

from sqlalchemy import select

from app.agent import model_output, model_router, usage
from app.agent.agent_call import FUNCTION_NAME, NOTICE
from app.agent.agent_loop import run_agent
from app.agent.agent_tool_set import ExtraTools
from app.agent.analysis_agents import ANALYSIS_NOTICE, AnalysisAgent, build_agent_tools, load_agents
from app.agent.dispatch import dispatch_dossier_summary, dispatch_question_answers
from app.agent.documents import load_dossier
from app.agent.knowledge_tools import KnowledgeContext
from app.db import async_session_factory
from app.models.dossier import Dossier, DossierStatus, ExecutionStep, ExecutionStepStatus
from app.repositories.analyse_repository import AnalyseRepository
from app.repositories.dossier_repository import DossierRepository
from app.services.execution_steps import complete_step, reusable_agent_output
from app.services.internal_analyse import build_internal_analyse

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2  # secondes entre deux lectures de l'état des étapes
POLL_TIMEOUT = 600  # 10 minutes au plus à attendre la classification et l'extraction
WAITED_KINDS = ("classification", "extraction")
FINISHED = (ExecutionStepStatus.TERMINE, ExecutionStepStatus.ECHEC)


async def _wait_for_steps(dossier_id: uuid.UUID) -> bool:
    """Attend que la classification et l'extraction soient terminées (ou en échec : les agents travaillent alors avec
    des données partielles). Faux si le dossier a été arrêté ou supprimé entre-temps : les agents ne partent pas."""
    deadline = time.monotonic() + POLL_TIMEOUT
    while time.monotonic() < deadline:
        async with async_session_factory() as db:
            dossier_status = (
                await db.execute(select(Dossier.status).where(Dossier.id == dossier_id))
            ).scalar_one_or_none()
            statuses = (
                (
                    await db.execute(
                        select(ExecutionStep.status).where(
                            ExecutionStep.dossier_id == dossier_id, ExecutionStep.kind.in_(WAITED_KINDS)
                        )
                    )
                )
                .scalars()
                .all()
            )
        if dossier_status is None or dossier_status == DossierStatus.ARRETE:
            return False
        if all(status in FINISHED for status in statuses):
            return True
        await asyncio.sleep(POLL_INTERVAL)
    logger.warning("Dossier %s : classification et extraction non terminées après %ds", dossier_id, POLL_TIMEOUT)
    return True


async def _log(step_id: str | None, message: str, level: str = "info") -> None:
    if not step_id:
        return
    async with async_session_factory() as db:
        repository = DossierRepository(db)
        step = await repository.get_execution_step_by_id(uuid.UUID(step_id))
        if step is not None:
            await repository.add_log(step, level, message)


async def _complete(step_id: str | None, status: ExecutionStepStatus, output: str | None) -> None:
    if not step_id:
        return
    async with async_session_factory() as db:
        await complete_step(db, uuid.UUID(step_id), status, output)


def _step_of(dossier: dict, agent_name: str) -> dict | None:
    """L'étape d'un agent : ils partagent tous le kind « agent », on les distingue par leur nom."""
    return next(
        (s for s in dossier.get("execution_steps", []) if s["kind"] == "agent" and s["label"] == agent_name), None
    )


def _with_notice(prompt: str, extra: ExtraTools) -> str:
    """Le prompt de l'agent, suivi de ce qu'il doit savoir de ses outils (sorties externes, outils absents, analyse)."""
    notices = [extra.notice] if extra.notice else []
    notices.append(ANALYSIS_NOTICE)
    if extra.owns(FUNCTION_NAME):
        notices.append(NOTICE)
    return "\n\n".join([prompt, *notices])


async def _log_missing_tools(step_id: str | None, extra: ExtraTools) -> None:
    """Dit dans le journal de l'étape les outils qui n'ont pas été donnés à l'agent : l'exécution continue sans eux."""
    if extra.skipped:
        await _log(
            step_id, "Outils ignorés (retirés ou pas encore disponibles) : " + ", ".join(extra.skipped), "warning"
        )
    if extra.unavailable:
        await _log(
            step_id,
            f"{len(extra.unavailable)} outil(s) MCP non utilisables dans cette exécution (droits, session ou serveur)",
            "warning",
        )


async def _run_single_agent(
    dossier_id: str,
    analyse_id: str,
    agent: dict,
    others: list[AnalysisAgent],
    step_id: str | None,
    acting_user: str | None,
    knowledge: KnowledgeContext | None,
) -> None:
    await _log(step_id, f"Agent '{agent['name']}' démarré")
    run_id = f"agent-{dossier_id}-{agent.get('id', 'x')}-{uuid.uuid4().hex[:8]}"
    definition = AnalysisAgent(
        str(agent.get("id", "")), agent["name"], agent["prompt"], list(agent.get("tools", [])), agent.get("model")
    )
    # Le dossier à jour (avec les prédictions de la classification et de l'extraction), les outils choisis pour
    # l'agent et l'accès à son analyse : comme dans le chat, un autre agent peut lui répondre.
    tools, extra, _ = await build_agent_tools(
        agent=definition,
        dossier_id=dossier_id,
        analyse_id=analyse_id,
        acting_user=acting_user,
        run_id=run_id,
        knowledge=knowledge,
        allow_side_effects=True,
        others=[other for other in others if other.name != definition.name],
    )
    await _log_missing_tools(step_id, extra)
    # Le modèle de l'agent s'il en a un ; sinon le modèle par défaut, ou (mode auto) celui que sa consigne demande.
    model = await model_router.for_query(agent["prompt"], explicit=agent.get("model"))
    answer = await run_agent(prompt=_with_notice(agent["prompt"], extra), tools=tools, model=model)
    await _complete(step_id, ExecutionStepStatus.TERMINE, answer)
    logger.info("Agent '%s' terminé : %d caractères", agent["name"], len(answer))


async def run_agents(dossier_id: str, acting_user: str | None = None) -> None:
    """`acting_user` : la personne qui a lancé l'analyse ; les outils MCP sont appelés en son nom. Absente (exécution
    sans personne), seuls les outils internes sont utilisables."""
    usage.bind("run_agents", dossier_id=dossier_id)
    async with async_session_factory() as db:
        dossier_row = await DossierRepository(db).get(uuid.UUID(dossier_id))
        analyse = (
            await AnalyseRepository(db).get(dossier_row.analyse_id) if dossier_row and dossier_row.analyse_id else None
        )
        definitions = build_internal_analyse(analyse).model_dump(mode="json") if analyse else None
    if definitions is None:
        logger.warning("Dossier %s sans analyse : agents ignorés", dossier_id)
        return
    agents = definitions.get("agents", [])
    knowledge = KnowledgeContext(str(analyse.id), definitions.get("knowledge_collections", []))
    if not agents:
        logger.info("Aucun agent pour l'analyse %s", analyse.id)

    # Les agents lisent les prédictions de la classification et de l'extraction. Sans agent on attend aussi : le
    # résumé du dossier, lancé plus bas, s'appuie sur ces résultats.
    if not await _wait_for_steps(uuid.UUID(dossier_id)):
        logger.info("Dossier %s arrêté : agents non lancés", dossier_id)
        return

    others = await load_agents(str(analyse.id))
    for agent in agents:
        async with async_session_factory() as db:
            dossier = await load_dossier(db, dossier_id)
        step = _step_of(dossier, agent["name"])
        step_id = step["id"] if step else None
        if step is not None and step["status"] != ExecutionStepStatus.EN_COURS:
            continue  # déjà terminé (travail relancé) : on n'y touche pas
        # Relance incrémentale (#119) : agent et entrées inchangés, la synthèse de l'exécution précédente est reprise
        # sans appeler le LLM.
        if step_id:
            async with async_session_factory() as db:
                reused = await reusable_agent_output(db, uuid.UUID(dossier_id), uuid.UUID(step_id))
            # Une synthèse vide ou en JSON (appel d'outil écrit en texte) ne se reprend pas.
            if reused is not None and not model_output.unusable(reused):
                await _log(step_id, "Synthèse reprise de l'exécution précédente (entrées inchangées)")
                await _complete(step_id, ExecutionStepStatus.TERMINE, reused)
                logger.info("Agent '%s' repris pour le dossier %s", agent["name"], dossier_id)
                continue
        try:
            await _run_single_agent(dossier_id, str(analyse.id), agent, others, step_id, acting_user, knowledge)
        except Exception as error:
            logger.exception("Agent '%s' en échec pour le dossier %s", agent["name"], dossier_id)
            await _log(step_id, str(error), "error")
            await _complete(step_id, ExecutionStepStatus.ECHEC, str(error))

    # Tous les agents ont terminé, les synthèses sont disponibles : le résumé global du dossier (issue #52). Aussi pour
    # une analyse sans agent : sans cela, un dossier sans agent n'aurait jamais de résumé.
    dispatch_dossier_summary(dossier_id)
    # Les réponses aux questions fréquentes de l'analyse, prêtes pour la conversation (issue #422) : indépendantes du
    # résumé, elles se calculent en même temps.
    dispatch_question_answers(dossier_id)
