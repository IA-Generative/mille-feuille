"""Graphe LangGraph pour l'exécution d'un agent.

Le graphe suit un pattern ReAct simplifié :
1. Le LLM reçoit le prompt de l'agent + les outils disponibles.
2. S'il demande à appeler un outil, on l'exécute et on renvoie le résultat.
3. S'il ne demande pas d'outil, on considère la réponse comme finale.

Le graphe boucle (tool → agent → tool → ...) jusqu'à ce que le LLM
produise une réponse sans appel d'outil, ou jusqu'à AGENT_MAX_ITERATIONS.

État du graphe :
- messages : historique des messages (system, user, assistant, tool)
- agent_prompt : prompt système de l'agent
- tools : instance d'AgentTools
- iteration : compteur d'itérations
"""

import json
import logging
from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from app.config import settings
from app.llm import _client
from app.tools import AgentTools

logger = logging.getLogger(__name__)


class AgentState(TypedDict, total=False):
    """État du graphe LangGraph."""

    messages: list[dict[str, Any]]
    agent_prompt: str
    model: str | None
    tools: AgentTools
    iteration: int
    final_answer: str


def _agent_node(state: AgentState) -> AgentState:
    """Nœud agent : appelle le LLM avec les messages et les outils.
    Si le LLM demande un outil, on prépare l'appel. Sinon, on stocke la
    réponse finale."""
    client = _client()
    model = state.get("model") or settings.LLM_MODEL
    tools = state["tools"]

    messages: list[dict[str, Any]] = [{"role": "system", "content": state["agent_prompt"]}]
    messages.extend(state["messages"])

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools.tool_definitions(),
        tool_choice="auto",
        parallel_tool_calls=False,
        temperature=0.2,
        max_tokens=2000,
    )

    choice = response.choices[0]
    assistant_msg: dict[str, Any] = {
        "role": "assistant",
        "content": choice.message.content or "",
    }

    if choice.message.tool_calls:
        assistant_msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in choice.message.tool_calls
        ]

    state["messages"] = state.get("messages", []) + [assistant_msg]
    state["iteration"] = state.get("iteration", 0) + 1
    return state


def _should_continue(state: AgentState) -> str:
    """Condition : continue vers les outils si le LLM a demandé un appel
    d'outil, sinon termine."""
    last_msg = state["messages"][-1] if state.get("messages") else {}
    if last_msg.get("tool_calls"):
        if state.get("iteration", 0) >= settings.AGENT_MAX_ITERATIONS:
            logger.warning(
                "Agent reached max iterations (%d), stopping",
                settings.AGENT_MAX_ITERATIONS,
            )
            return "end"
        return "tools"
    state["final_answer"] = last_msg.get("content", "")
    return "end"


def _tools_node(state: AgentState) -> AgentState:
    """Nœud outils : exécute tous les tool_calls demandés par le LLM et
    ajoute les résultats comme messages tool."""
    tools = state["tools"]
    last_msg = state["messages"][-1]
    new_messages: list[dict[str, Any]] = []

    for tc in last_msg.get("tool_calls", []):
        name = tc["function"]["name"]
        try:
            arguments = json.loads(tc["function"]["arguments"])
        except json.JSONDecodeError:
            arguments = {}
        logger.info("Tool call: %s(%s)", name, arguments)
        result = tools.dispatch_tool(name, arguments)
        new_messages.append(
            {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            }
        )

    state["messages"] = state.get("messages", []) + new_messages
    return state


def build_agent_graph() -> Any:
    """Construit le graphe LangGraph pour l'exécution d'un agent.
    Le graphe : agent → (tools → agent)* → END"""
    graph = StateGraph(AgentState)
    graph.add_node("agent", _agent_node)
    graph.add_node("tools", _tools_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges(
        "agent",
        _should_continue,
        {"tools": "tools", "end": END},
    )
    graph.add_edge("tools", "agent")
    return graph.compile()


def run_agent(
    agent_prompt: str,
    tools: AgentTools,
    model: str | None = None,
) -> str:
    """Exécute un agent avec son prompt et ses outils. Renvoie la réponse
    finale (synthèse) produite par le LLM."""
    graph = build_agent_graph()
    initial_state: AgentState = {
        # Certains serveurs LLM exigent un message user pour injecter les outils.
        "messages": [
            {
                "role": "user",
                "content": (
                    "Exécute la tâche décrite dans tes instructions en utilisant "
                    "les outils disponibles, puis produis ta réponse finale."
                ),
            }
        ],
        "agent_prompt": agent_prompt,
        "model": model,
        "tools": tools,
        "iteration": 0,
    }
    final_state = graph.invoke(initial_state)
    answer = final_state.get("final_answer", "")
    if not answer:
        last_msg = final_state.get("messages", [{}])[-1]
        answer = last_msg.get("content", "Aucune réponse produite.")
    logger.info(
        "Agent completed in %d iterations, answer length: %d",
        final_state.get("iteration", 0),
        len(answer),
    )
    return answer
