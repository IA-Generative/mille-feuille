"""Un agent de l'analyse répond dans le chat du dossier.

Les agents d'une analyse ne tournent pas qu'à la fin du pipeline : quand la question de la personne relève du rôle de
l'un d'eux (le plan le décide, voir planner.py), c'est lui qui répond, avec son prompt, ses outils et la synthèse qu'il
a déjà produite sur ce dossier. Tout ce qui le concerne (outils, accès à l'analyse, appel d'un autre agent) est dans
`analysis_agents.py`, commun à l'exécution de l'analyse."""

import logging
import uuid
from typing import Any

from app.agent.analysis_agents import AnalysisAgent, converse
from app.agent.chat.events import ChatEvents
from app.agent.knowledge_tools import KnowledgeContext
from app.agent.tools import AgentTools

logger = logging.getLogger(__name__)


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
