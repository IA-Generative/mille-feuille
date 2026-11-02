"""Un agent en interroge un autre (`appel_agent`) : il lui pose une question et reçoit sa réponse.

Pas de récursion : l'agent appelé n'a pas l'outil. Et pas d'emballement : un nombre borné d'appels par exécution."""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.agent.analysis_agents import AnalysisAgent

TOOL_ID = "appel_agent"
FUNCTION_NAME = "ask_agent"
MAX_CALLS = 3

NOTICE = (
    "Tu peux interroger un autre agent de l'analyse avec ask_agent quand sa spécialité te manque : pose-lui une "
    "question précise, il répond à partir du même dossier."
)


class AgentCaller:
    def __init__(
        self,
        others: list["AnalysisAgent"],
        ask: Callable[["AnalysisAgent", str], Awaitable[str]],
        limit: int = MAX_CALLS,
    ) -> None:
        self._others = others
        self._ask = ask
        self._limit = limit
        self._calls = 0

    def definition(self) -> dict[str, Any]:
        names = [agent.name for agent in self._others]
        return {
            "type": "function",
            "function": {
                "name": FUNCTION_NAME,
                "description": "Pose une question à un autre agent de l'analyse et rend sa réponse. Agents : "
                + "; ".join(f"{agent.name} ({agent.summary})" for agent in self._others),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string", "enum": names, "description": "Le nom de l'agent interrogé"},
                        "question": {"type": "string", "description": "Ta question, complète et sans ambiguïté"},
                    },
                    "required": ["agent", "question"],
                },
            },
        }

    async def run(self, arguments: dict[str, Any]) -> str:
        name, question = str(arguments.get("agent", "")).strip(), str(arguments.get("question", "")).strip()
        target = next((agent for agent in self._others if agent.name.casefold() == name.casefold()), None)
        if target is None:
            return f"Agent « {name} » inconnu. Agents disponibles : {', '.join(a.name for a in self._others)}."
        if not question:
            return "Erreur : la question est vide."
        if self._calls >= self._limit:
            return f"Limite atteinte : {self._limit} appels d'agents par exécution. Réponds avec ce que tu as."
        self._calls += 1
        try:
            return await self._ask(target, question)
        except Exception as error:  # noqa: BLE001 - l'agent qui appelle continue sans cette réponse
            return f"L'agent « {target.name} » n'a pas pu répondre : {error}"
