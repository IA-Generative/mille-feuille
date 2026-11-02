"""Les agents d'une analyse, et ce qu'il faut pour en faire répondre un : outils, synthèse, accès à son analyse.

Deux appelants s'en servent : l'exécution d'une analyse (`jobs/agents.py`), qui lui donne une tâche, et le chat du
dossier (`chat/agent_reply.py`), qui lui donne la conversation. Un agent peut aussi en interroger un autre
(`agent_call.py`) : celui-là répond sans pouvoir, à son tour, en appeler un troisième."""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from app.agent.agent_call import FUNCTION_NAME, NOTICE, TOOL_ID, AgentCaller
from app.agent.agent_loop import OnEvent, run_agent
from app.agent.agent_tool_set import ExtraTools, build_extra_tools
from app.agent.analysis_reader import AnalysisReader
from app.agent.documents import load_dossier
from app.agent.knowledge_tools import KnowledgeContext
from app.agent.tools import AgentTools
from app.db import async_session_factory
from app.repositories.analyse_repository import AnalyseRepository
from app.services.search.retrieval import DossierSearcher

logger = logging.getLogger(__name__)

SUMMARY_CHARS = 200

CHAT_INSTRUCTIONS = (
    "Tu réponds ici à une personne qui t'interroge dans le chat du dossier, en tant que cet agent : reste dans ton "
    "rôle, appuie-toi sur le dossier avec tes outils, cite les pages que tu as lues, et dis-le franchement quand "
    "le dossier ne permet pas de répondre."
)
ANALYSIS_NOTICE = (
    "Tu peux lire l'analyse à laquelle tu appartiens (read_analysis, list_agents, read_agent_output, view_analysis) : "
    "sa définition, ses éléments et les synthèses des autres agents. Elle est en lecture seule."
)


@dataclass(frozen=True)
class AnalysisAgent:
    ref: str
    name: str
    prompt: str
    tools: list[str]
    model: str | None
    id: str = ""  # l'identifiant en base (celui de l'index de recherche)

    @property
    def summary(self) -> str:
        """Ce que le plan lit de l'agent : le début de son prompt, sur une ligne."""
        text = " ".join(self.prompt.split())
        return text[:SUMMARY_CHARS] + ("…" if len(text) > SUMMARY_CHARS else "") or "(sans description)"


async def load_agents(analyse_id: str | None) -> list[AnalysisAgent]:
    """Les agents de l'analyse, dans son ordre ; la référence est leur rang (1, 2, ...), plus sûre à recopier pour un
    modèle qu'un identifiant."""
    if not analyse_id:
        return []
    async with async_session_factory() as db:
        analyse = await AnalyseRepository(db).get(uuid.UUID(analyse_id))
        if analyse is None:
            return []
        return [
            AnalysisAgent(str(rank), agent.name, agent.prompt, list(agent.tools), agent.model, str(agent.id))
            for rank, agent in enumerate(analyse.agents, start=1)
        ]


def synthesis_of(dossier: dict, agent: AnalysisAgent) -> str | None:
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


def conversation_prompt(agent: AnalysisAgent, synthesis: str | None, notices: list[str]) -> str:
    parts = [agent.prompt, CHAT_INSTRUCTIONS, *notices]
    parts.append(
        f"--- Ta synthèse sur ce dossier ---\n{synthesis}"
        if synthesis
        else "Tu n'as pas encore de synthèse sur ce dossier : travaille à partir du dossier lui-même."
    )
    return "\n\n".join(parts)


async def build_agent_tools(
    *,
    agent: AnalysisAgent,
    dossier_id: str,
    analyse_id: str | None,
    acting_user: str | None,
    run_id: str,
    knowledge: KnowledgeContext | None,
    allow_side_effects: bool,
    others: list[AnalysisAgent] | None = None,
) -> tuple[AgentTools, ExtraTools, dict]:
    """Les outils d'un agent, son dossier à jour (avec les prédictions de la classification et de l'extraction) et son
    accès à l'analyse. `others` : les agents qu'il peut interroger ; vide pour un agent déjà interrogé par un autre."""
    async with async_session_factory() as db:
        fresh = await load_dossier(db, dossier_id)
    caller = None
    if others:

        async def ask(target: AnalysisAgent, question: str) -> str:
            answer, _ = await converse(
                agent=target,
                dossier_id=dossier_id,
                analyse_id=analyse_id,
                history=[{"role": "user", "content": question}],
                acting_user=acting_user,
                run_id=f"{run_id}-{target.ref}",
                knowledge=knowledge,
                model=None,
                allow_side_effects=allow_side_effects,
            )
            return answer

        caller = AgentCaller(others, ask)
    extra = await build_extra_tools(
        agent.tools,
        acting_user=acting_user,
        run_id=run_id,
        allow_side_effects=allow_side_effects,
        knowledge=knowledge,
        agent_caller=caller,
    )
    reader = AnalysisReader(dossier=fresh, analyse_id=analyse_id, user_id=acting_user or "")
    await reader.load()
    tools = AgentTools(fresh, extra=extra, searcher=DossierSearcher(dossier_id), reader=reader)
    return tools, extra, fresh


async def converse(
    *,
    agent: AnalysisAgent,
    dossier_id: str,
    analyse_id: str | None,
    history: list[dict[str, Any]],
    acting_user: str | None,
    run_id: str,
    knowledge: KnowledgeContext | None,
    model: str | None,
    allow_side_effects: bool,
    others: list[AnalysisAgent] | None = None,
    on_event: OnEvent | None = None,
) -> tuple[str, AgentTools]:
    """La réponse de l'agent à une conversation, et ses outils (pour déposer les pages qu'il a lues comme sources)."""
    tools, extra, fresh = await build_agent_tools(
        agent=agent,
        dossier_id=dossier_id,
        analyse_id=analyse_id,
        acting_user=acting_user,
        run_id=run_id,
        knowledge=knowledge,
        allow_side_effects=allow_side_effects,
        others=others,
    )
    notices = [extra.notice] if extra.notice else []
    notices.append(ANALYSIS_NOTICE)
    if extra.owns(FUNCTION_NAME):
        notices.append(NOTICE)
    answer = await run_agent(
        prompt=conversation_prompt(agent, synthesis_of(fresh, agent), notices),
        tools=tools,
        model=agent.model or model,
        history=history,
        on_event=on_event,
    )
    return answer, tools


__all__ = ["TOOL_ID", "AnalysisAgent", "converse", "load_agents"]
