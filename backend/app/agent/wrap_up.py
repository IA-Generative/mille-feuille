"""La dernière réponse d'une boucle d'outils qui a atteint sa limite d'appels. Sans elle, la personne ne lisait que le
dernier message du modèle (« je vais chercher… ») et les sources des pages lues, sans réponse : on redemande une
réponse écrite à partir de ce qui a déjà été lu, sans lui laisser appeler d'autre outil."""

import logging
from typing import Any

from app.agent import llm

logger = logging.getLogger(__name__)

WRAP_UP_NOTICE = (
    "Tu as atteint la limite d'appels d'outils. N'en appelle plus : réponds maintenant à la personne par un texte en "
    "français, à partir de ce que tu as déjà lu. Dis franchement ce qui manque pour répondre complètement."
)


async def wrap_up(
    *, model: str, messages: list[dict[str, Any]], definitions: list[dict[str, Any]], temperature: float = 0.2
) -> str:
    """Le texte de la réponse finale ; vide si le modèle n'a rien écrit ou si l'appel échoue (l'appelant a un repli).
    `messages` se termine par des résultats d'outils (ou par la demande de la personne) : il est cohérent tel quel."""
    try:
        response = await llm.complete(
            model=model,
            messages=[*messages, {"role": "user", "content": WRAP_UP_NOTICE}],
            tools=definitions,
            tool_choice="none",
            temperature=temperature,
            max_tokens=2000,
        )
    except Exception:
        logger.warning("Réponse finale après la limite d'appels impossible", exc_info=True)
        return ""
    return response.choices[0].message.content or ""
