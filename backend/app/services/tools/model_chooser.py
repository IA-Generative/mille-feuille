"""Le modèle choisit les arguments d'un tool : il n'a que ce tool, et on le **force** à l'appeler. Le client du hub est
isolé derrière `ToolChooser` : le service de test en dépend, les tests le remplacent par un faux."""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

SYSTEM_PROMPT = (
    "Tu testes un outil. Appelle-le une seule fois, avec les arguments qui correspondent à la demande de la "
    "personne. N'ajoute rien d'autre."
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChosenCall:
    model: str
    # None : le modèle n'a pas appelé l'outil (ou avec des arguments illisibles) ; `answer` dit ce qu'il a répondu.
    arguments: dict[str, Any] | None
    answer: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class ModelUnavailableError(Exception):
    """Le hub de modèles n'est pas configuré ou n'a pas répondu ; le message est affichable."""


class ToolChooser(Protocol):
    async def choose(self, model: str | None, prompt: str, tool: ToolSpec) -> ChosenCall: ...


def _parse_arguments(raw: str | None) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class OpenAiToolChooser:
    """Client réel : hub compatible OpenAI. `default_model` donne le premier modèle capable de chat du hub."""

    def __init__(self, client: Any, default_model: Callable[[], Awaitable[str | None]]) -> None:
        self._client = client
        self._default_model = default_model

    async def choose(self, model: str | None, prompt: str, tool: ToolSpec) -> ChosenCall:
        if self._client is None:
            raise ModelUnavailableError("Le hub de modèles n'est pas configuré.")
        try:
            model = model or await self._default_model()
            if model is None:
                raise ModelUnavailableError("Aucun modèle de chat n'est disponible sur le hub.")
            completion = await self._client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.input_schema or {"type": "object", "properties": {}},
                        },
                    }
                ],
                tool_choice="required",
            )
        except ModelUnavailableError:
            raise
        except Exception as error:  # le SDK lève des erreurs variées (réseau, quota, modèle inconnu…)
            raise ModelUnavailableError("Le modèle n'a pas répondu.") from error
        message = completion.choices[0].message
        usage = completion.usage
        calls = message.tool_calls or []
        return ChosenCall(
            model=model,
            arguments=_parse_arguments(calls[0].function.arguments) if calls else None,
            answer=message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )
