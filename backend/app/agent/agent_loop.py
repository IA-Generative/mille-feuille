"""Un agent : son prompt, des outils, et une boucle (le modèle appelle des outils jusqu'à avoir de quoi conclure).
C'est celle des agents d'analyse, qui travaillent sans personne (pas de question à choix, pas de demande d'accord), et
celle de l'assistant de l'application, qui converse (historique et événements en plus)."""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.agent import llm, model_output
from app.agent.runner import settings
from app.agent.wrap_up import wrap_up

logger = logging.getLogger(__name__)

# Certains serveurs LLM exigent un message de la personne pour donner les outils au modèle.
TASK = (
    "Exécute la tâche décrite dans tes instructions en utilisant les outils disponibles, puis produis ta réponse "
    "finale."
)
NO_ANSWER = "Aucune réponse produite."


def _arguments_of(call: dict[str, Any]) -> dict[str, Any]:
    try:
        arguments = json.loads(call["function"]["arguments"])
    except json.JSONDecodeError:
        return {}
    return arguments if isinstance(arguments, dict) else {}


# Une étape visible de la personne : kind (tool_call, tool_result) et données.
OnEvent = Callable[[str, dict], Awaitable[None]]
PREVIEW_CHARS = 200


async def run_agent(
    *,
    prompt: str,
    tools: Any,
    model: str | None = None,
    history: list[dict[str, Any]] | None = None,
    on_event: OnEvent | None = None,
) -> str:
    """La synthèse de l'agent : sa dernière réponse, une fois qu'il n'appelle plus d'outil. Sans `history`, l'agent
    exécute la tâche de ses instructions ; avec, il répond à la conversation. `tools` : un jeu d'outils
    (`tool_definitions()` et `dispatch_tool()`)."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prompt},
        *(history if history is not None else [{"role": "user", "content": TASK}]),
    ]
    retried = False
    for iteration in range(1, settings.AGENT_MAX_ITERATIONS + 1):
        definitions = tools.tool_definitions()
        response = await llm.complete(
            model=model or settings.LLM_MODEL,
            messages=messages,
            tools=definitions,
            tool_choice="auto",
            parallel_tool_calls=False,
            temperature=0.2,
            max_tokens=2000,
        )
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
                logger.warning("Agent : appel d'outil écrit en texte repris (%s)", recovered["function"]["name"])
                if on_event:
                    await on_event("note", {"text": "Le modèle a écrit un appel d'outil en texte : il a été repris."})
                calls, content = [recovered], ""
            elif model_output.unusable(content) and not retried:
                logger.warning(
                    "Agent : réponse inexploitable du modèle (%d caractères), nouvelle demande", len(content)
                )
                retried = True
                if on_event:
                    await on_event("note", {"text": "Réponse vide ou en JSON : le modèle a été relancé une fois."})
                if content.strip():
                    messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": model_output.RETRY_NOTICE})
                continue
            else:
                logger.info("Agent terminé en %d itération(s) : %d caractères", iteration, len(content))
                return content if not model_output.unusable(content) else NO_ANSWER
        messages.append({"role": "assistant", "content": content, "tool_calls": calls})
        for call in calls:
            name, arguments = call["function"]["name"], _arguments_of(call)
            logger.info("Appel d'outil de l'agent : %s(%s)", name, arguments)
            if on_event:
                await on_event("tool_call", {"tool_name": name, "arguments": arguments})
            result = await tools.dispatch_tool(name, arguments)
            if on_event:
                preview = result[:PREVIEW_CHARS] + "..." if len(result) > PREVIEW_CHARS else result
                await on_event("tool_result", {"tool_name": name, "preview": preview, "full": result})
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
    logger.warning("Agent : %d itérations atteintes, réponse finale demandée", settings.AGENT_MAX_ITERATIONS)
    if on_event:
        await on_event("note", {"text": "Limite d'appels d'outils atteinte : une réponse finale a été demandée."})
    final = await wrap_up(model=model or settings.LLM_MODEL, messages=messages, definitions=tools.tool_definitions())
    return final if not model_output.unusable(final) else NO_ANSWER
