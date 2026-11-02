"""Un agent de l'analyse répond dans le chat du dossier.

Les agents d'une analyse ne tournent pas qu'à la fin du pipeline : quand la question de la personne relève du rôle de
l'un d'eux (le plan le décide, voir planner.py), c'est lui qui répond, avec son prompt, ses outils et la synthèse qu'il
a déjà produite sur ce dossier."""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from app.agent.agent_loop import run_agent
from app.agent.agent_tool_set import build_extra_tools
from app.agent.chat.events import ChatEvents
from app.agent.documents import load_dossier
from app.agent.knowledge_tools import KnowledgeContext
from app.agent.tools import AgentTools
from app.db import async_session_factory
from app.repositories.analyse_repository import AnalyseRepository
from app.services.search.retrieval import DossierSearcher

logger = logging.getLogger(__name__)

SUMMARY_CHARS = 200

_INSTRUCTIONS = (
    "Tu réponds ici à une personne qui t'interroge dans le chat du dossier, en tant que cet agent : reste dans ton "
    "rôle, appuie-toi sur le dossier avec tes outils, cite les pages que tu as lues, et dis-le franchement quand "
    "le dossier ne permet pas de répondre."
)


@dataclass(frozen=True)
class ChatAgent:
    ref: str
    name: str
    prompt: str
    tools: list[str]
    model: str | None

    @property
    def summary(self) -> str:
        """Ce que le plan lit de l'agent : le début de son prompt, sur une ligne."""
        text = " ".join(self.prompt.split())
        return text[:SUMMARY_CHARS] + ("…" if len(text) > SUMMARY_CHARS else "") or "(sans description)"


async def load_agents(analyse_id: str | None) -> list[ChatAgent]:
    """Les agents de l'analyse du dossier, dans l'ordre de l'analyse ; la référence est leur rang (1, 2, ...), plus sûre
    à recopier pour un modèle qu'un identifiant."""
    if not analyse_id:
        return []
    async with async_session_factory() as db:
        analyse = await AnalyseRepository(db).get(uuid.UUID(analyse_id))
        if analyse is None:
            return []
        return [
            ChatAgent(str(rank), agent.name, agent.prompt, list(agent.tools), agent.model)
            for rank, agent in enumerate(analyse.agents, start=1)
        ]


def agents_for_plan(agents: list[ChatAgent]) -> list[dict]:
    return [{"ref": agent.ref, "name": agent.name, "summary": agent.summary} for agent in agents]


def _synthesis_of(dossier: dict, agent: ChatAgent) -> str | None:
    """La synthèse que l'agent a produite sur ce dossier (les agents ne partagent que le kind « agent » : on les
    distingue par leur nom)."""
    return next(
        (
            step["output"]
            for step in dossier.get("execution_steps", [])
            if step.get("kind") == "agent" and step.get("label") == agent.name and step.get("output")
        ),
        None,
    )


def _prompt(agent: ChatAgent, synthesis: str | None, notice: str) -> str:
    parts = [agent.prompt, _INSTRUCTIONS]
    if notice:
        parts.append(notice)
    parts.append(
        f"--- Ta synthèse sur ce dossier ---\n{synthesis}"
        if synthesis
        else "Tu n'as pas encore de synthèse sur ce dossier : travaille à partir du dossier lui-même."
    )
    return "\n\n".join(parts)


async def answer_as_agent(
    *,
    agent: ChatAgent,
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
    n'a pas le sien."""
    dossier_id = dossier["id"]
    async with async_session_factory() as db:
        fresh = await load_dossier(db, dossier_id)
    extra = await build_extra_tools(
        agent.tools,
        acting_user=acting_user,
        run_id=f"chat-agent-{conversation_id}-{uuid.uuid4().hex[:8]}",
        allow_side_effects=False,
        knowledge=knowledge,
    )
    tools = AgentTools(fresh, extra=extra, searcher=DossierSearcher(dossier_id))
    await events.emit("thinking", {"agent": agent.name})

    async def on_event(kind: str, data: dict) -> None:
        await events.emit(kind, {**data, "agent": agent.name})

    answer = await run_agent(
        prompt=_prompt(agent, _synthesis_of(fresh, agent), extra.notice),
        tools=tools,
        model=agent.model or model,
        history=history,
        on_event=on_event,
    )
    logger.info("Agent '%s' a répondu dans le chat (conversation %s)", agent.name, conversation_id)
    return answer, tools
