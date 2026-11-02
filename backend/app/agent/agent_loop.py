"""Un agent d'analyse : son prompt, des outils, et une boucle (le modèle appelle des outils jusqu'à avoir de quoi
conclure). Il travaille sans personne : pas de question à choix, pas de demande d'accord."""

import json
import logging
from typing import Any

from app.agent import llm
from app.agent.runner import settings
from app.agent.tools import AgentTools

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


async def run_agent(*, prompt: str, tools: AgentTools, model: str | None = None) -> str:
    """La synthèse de l'agent : sa dernière réponse, une fois qu'il n'appelle plus d'outil."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": prompt}, {"role": "user", "content": TASK}]
    for iteration in range(1, settings.AGENT_MAX_ITERATIONS + 1):
        response = await llm.complete(
            model=model or settings.LLM_MODEL,
            messages=messages,
            tools=tools.tool_definitions(),
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
            logger.info("Agent terminé en %d itération(s) : %d caractères", iteration, len(content))
            return content or NO_ANSWER
        messages.append({"role": "assistant", "content": content, "tool_calls": calls})
        for call in calls:
            name, arguments = call["function"]["name"], _arguments_of(call)
            logger.info("Appel d'outil de l'agent : %s(%s)", name, arguments)
            result = await tools.dispatch_tool(name, arguments)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
    logger.warning("Agent : %d itérations atteintes, arrêt", settings.AGENT_MAX_ITERATIONS)
    return messages[-1].get("content") if messages[-1]["role"] == "assistant" else NO_ANSWER
