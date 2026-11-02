"""La boucle d'outils du chat : le modèle appelle des outils (notes, correction de l'analyse, serveurs MCP, lecture de
pages, question à choix) jusqu'à avoir de quoi répondre. C'est le chemin des demandes d'agir, et le repli quand la
recherche ne donne rien. Une demande d'accord (outil qui modifie des données) ou une question à choix arrête la boucle :
la tâche se termine, la personne répond quand elle veut, et sa réponse relance le chat."""

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.agent import llm, model_output
from app.agent.ask_user import ASK_USER
from app.agent.chat.events import ChatEvents
from app.agent.runner import settings
from app.agent.tools import AgentTools
from app.agent.wrap_up import wrap_up

logger = logging.getLogger(__name__)

MAX_CALLS_PER_BATCH = 5  # le plafond du backend (schemas/chat_tool_call.py)
CONFIRMATION_TEXT = "J'ai besoin de votre accord avant d'utiliser un outil qui modifie des données."
QUESTION_TEXT = "J'ai une question avant de continuer."
PREVIEW_CHARS = 200


@dataclass
class LoopResult:
    answer: str
    # Les appels du tour attendent la personne (accord ou réponse) : voir `tools.confirmation_batch`.
    awaiting: bool = False
    iterations: int = 0


def _arguments_of(call: dict[str, Any]) -> dict[str, Any]:
    try:
        arguments = json.loads(call["function"]["arguments"])
    except json.JSONDecodeError:
        return {}
    return arguments if isinstance(arguments, dict) else {}


async def _ask_confirmation(tools: AgentTools, events: ChatEvents, calls: list[dict[str, Any]], said: str) -> str:
    """Un des appels modifie des données : rien n'est exécuté pour lui. Les appels de ce tour sont enregistrés (les
    outils en lecture seule sont exécutés, leur résultat sert à rebâtir l'historique)."""
    batch: list[dict[str, Any]] = []
    for call in calls[:MAX_CALLS_PER_BATCH]:
        name = call["function"]["name"]
        arguments = _arguments_of(call)
        record: dict[str, Any] = {"llm_call_id": call["id"], "function_name": name, "arguments": arguments}
        if tools.requires_confirmation(name):
            record |= tools.confirmation_info(name) | {"side_effect": True, "status": "pending"}
        else:
            await events.emit("tool_call", {"tool_name": name, "arguments": arguments})
            record |= {
                "tool_id": name,
                "tool_name": name,
                "side_effect": False,
                "status": "executed",
                "result": await tools.dispatch_tool(name, arguments),
            }
        batch.append(record)
    if len(calls) > MAX_CALLS_PER_BATCH:
        logger.warning("Chat: %d appels d'outils demandés, %d gardés", len(calls), MAX_CALLS_PER_BATCH)
    tools.confirmation_batch = batch
    return said or CONFIRMATION_TEXT


def _ask_question(tools: AgentTools, call: dict[str, Any], questions: list[dict[str, Any]], said: str) -> str:
    """Le modèle pose une question à choix : elle est enregistrée avec le message, la réponse de la personne sera le
    résultat de l'appel. Les autres appels de ce tour sont écartés (le modèle les redemandera)."""
    tools.confirmation_batch = [
        {
            "llm_call_id": call["id"],
            "function_name": ASK_USER,
            "tool_id": ASK_USER,
            "tool_name": ASK_USER,
            "arguments": {"questions": questions},
            "side_effect": False,
            "status": "pending",
        }
    ]
    return said or QUESTION_TEXT


def store_question(tools: AgentTools, questions: list[dict[str, Any]]) -> str:
    """Une question du plan (« clarify »), enregistrée comme le serait un appel à `ask_user`."""
    return _ask_question(tools, {"id": "plan-clarify"}, questions, "")


async def run_tool_loop(
    *, model: str | None, system_prompt: str, messages: list[dict[str, Any]], tools: AgentTools, events: ChatEvents
) -> LoopResult:
    """Fait tourner le modèle avec les outils. `messages` est l'historique (le dernier message est celui de la
    personne) ; il n'est pas modifié."""
    conversation = [{"role": "system", "content": system_prompt}, *messages]
    iterations = 0
    retried = False
    while True:
        definitions = tools.tool_definitions()
        response = await llm.complete(
            model=model or settings.LLM_MODEL,
            messages=conversation,
            tools=definitions,
            tool_choice="auto",
            parallel_tool_calls=False,
            temperature=0.2,
            max_tokens=2000,
        )
        iterations += 1
        message = response.choices[0].message
        content = message.content or ""
        calls = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments},
            }
            for call in message.tool_calls or []
        ]
        if not calls:
            # Un appel d'outil écrit en texte est exécuté comme s'il avait été fait par l'API ; une réponse vide ou en
            # JSON est redemandée une fois.
            recovered = model_output.recovered_call(content, model_output.tool_names(definitions))
            if recovered:
                logger.warning("Chat: appel d'outil écrit en texte repris (%s)", recovered["function"]["name"])
                events.note("Le modèle a écrit un appel d'outil en texte : il a été repris et exécuté.")
                calls, content = [recovered], ""
            elif model_output.unusable(content) and not retried and iterations < settings.AGENT_MAX_ITERATIONS:
                logger.warning("Chat: réponse inexploitable du modèle (%d caractères), nouvelle demande", len(content))
                retried = True
                events.note("Réponse vide ou en JSON : le modèle a été relancé une fois.")
                if content.strip():
                    conversation.append({"role": "assistant", "content": content})
                conversation.append({"role": "user", "content": model_output.RETRY_NOTICE})
                continue
            else:
                return LoopResult(answer=model_output.shown(content), iterations=iterations)
        if iterations >= settings.AGENT_MAX_ITERATIONS:
            logger.warning("Chat: %d itérations atteintes, réponse finale demandée", settings.AGENT_MAX_ITERATIONS)
            events.note("Limite d'appels d'outils atteinte : une réponse finale a été demandée sans outil.")
            final = await wrap_up(model=model or settings.LLM_MODEL, messages=conversation, definitions=definitions)
            return LoopResult(answer=model_output.shown(final or content), iterations=iterations)

        for call in calls:
            questions = tools.question_to_ask(call["function"]["name"], _arguments_of(call))
            if questions:
                return LoopResult(_ask_question(tools, call, questions, content), awaiting=True, iterations=iterations)
        if any(tools.requires_confirmation(call["function"]["name"]) for call in calls):
            answer = await _ask_confirmation(tools, events, calls, content)
            return LoopResult(answer, awaiting=True, iterations=iterations)

        conversation.append({"role": "assistant", "content": content, "tool_calls": calls})
        for call in calls:
            name = call["function"]["name"]
            arguments = _arguments_of(call)
            # Le navigateur peut afficher « Recherche en cours… » pendant l'exécution.
            await events.emit("tool_call", {"tool_name": name, "arguments": arguments})
            logger.info("Chat tool call: %s(%s)", name, arguments)
            result = await tools.dispatch_tool(name, arguments)
            preview = result[:PREVIEW_CHARS] + "..." if len(result) > PREVIEW_CHARS else result
            await events.emit("tool_result", {"tool_name": name, "preview": preview, "full": result})
            conversation.append({"role": "tool", "tool_call_id": call["id"], "content": result})
