"""Un agent de l'analyse répond dans le chat du dossier.

Les agents d'une analyse ne tournent pas qu'à la fin du pipeline : quand la question de la personne relève du rôle de
l'un d'eux (le plan le décide, voir planner.py), c'est lui qui répond, avec son prompt, ses outils et la synthèse qu'il
a déjà produite sur ce dossier. Tout ce qui le concerne (outils, accès à l'analyse, appel d'un autre agent) est dans
`analysis_agents.py`, commun à l'exécution de l'analyse."""

import logging
import re
import uuid
from typing import Any

from app.agent.analysis_agents import AnalysisAgent, converse
from app.agent.chat.events import ChatEvents
from app.agent.knowledge_tools import KnowledgeContext
from app.agent.tools import AgentTools
from app.db import async_session_factory
from app.repositories.analyse_repository import AnalyseRepository
from app.services.search import agent_index

logger = logging.getLogger(__name__)


# Combien d'agents le plan lit au plus : au-delà, seuls les plus proches de la question lui sont donnés.
SHORTLIST = 4


async def shortlist(analyse_id: str | None, question: str, agents: list[AnalysisAgent]) -> list[AnalysisAgent]:
    """Les agents que le plan peut choisir : tous quand ils sont peu nombreux, sinon les `SHORTLIST` plus proches de la
    question par recherche hybride (voir services/search/agent_index.py), la référence de chacun restant son rang dans
    l'analyse. Sans index (Qdrant ou modèle d'embeddings absents) ou en cas d'erreur, tous : un choix moins ciblé vaut
    mieux qu'un chat en échec."""
    if len(agents) <= SHORTLIST or not analyse_id or not question.strip() or not agent_index.configured():
        return agents
    try:
        async with async_session_factory() as db:
            analyse = await AnalyseRepository(db).get(uuid.UUID(analyse_id))
        model = agent_index.embedding_model_of(analyse.search_settings if analyse else None)
        if not model:
            return agents
        ranked = await agent_index.find(analyse_id, question, model, SHORTLIST)
    except Exception:
        logger.warning("Agents de l'analyse %s non recherchés : tous sont proposés", analyse_id, exc_info=True)
        return agents
    by_id = {agent.id: agent for agent in agents}
    found = [by_id[agent_id] for agent_id in ranked if agent_id in by_id]
    return found or agents


def mentioned(question: str, agents: list[AnalysisAgent]) -> tuple[AnalysisAgent, str] | None:
    """L'agent que la personne a nommé avec `@Nom` (sans tenir compte de la casse), et sa question sans la mention. Une
    mention appelle l'agent à coup sûr : le plan n'a pas à le choisir. Le nom le plus long l'emporte (« @Agent 10 » n'est
    pas « @Agent 1 »), et un `@` collé à un mot (une adresse de courriel) n'est pas une mention."""
    for agent in sorted(agents, key=lambda candidate: len(candidate.name), reverse=True):
        found = re.search(rf"(?<!\w)@{re.escape(agent.name)}(?!\w)", question, flags=re.IGNORECASE)
        if found:
            rest = " ".join(f"{question[: found.start()]} {question[found.end() :]}".split())
            return agent, rest or question
    return None


def agents_for_plan(agents: list[AnalysisAgent]) -> list[dict]:
    return [{"ref": agent.ref, "name": agent.name, "summary": agent.summary} for agent in agents]


async def answer_as_agent(
    *,
    agent: AnalysisAgent,
    others: list[AnalysisAgent],
    dossier: dict,
    history: list[dict[str, Any]],
    events: ChatEvents,
    acting_user: str,
    conversation_id: str,
    knowledge: KnowledgeContext | None,
    model: str | None,
) -> tuple[str, AgentTools]:
    """La réponse de l'agent et ses outils (pour déposer les pages qu'il a lues comme sources du message).

    Les outils qui modifient des données ne lui sont pas donnés : dans le chat, une telle action passe par l'accord
    de la personne, ce que la boucle d'un agent ne sait pas demander. `model` : celui de la conversation, si l'agent
    n'a pas le sien. `others` : les agents qu'il peut interroger."""
    await events.emit("thinking", {"agent": agent.name})

    async def on_event(kind: str, data: dict) -> None:
        await events.emit(kind, {**data, "agent": agent.name})

    answer, tools = await converse(
        agent=agent,
        dossier_id=dossier["id"],
        analyse_id=dossier.get("analyse_id"),
        history=history,
        acting_user=acting_user,
        run_id=f"chat-agent-{conversation_id}-{uuid.uuid4().hex[:8]}",
        knowledge=knowledge,
        model=model,
        allow_side_effects=False,
        others=others,
        on_event=on_event,
    )
    logger.info("Agent '%s' a répondu dans le chat (conversation %s)", agent.name, conversation_id)
    return answer, tools
