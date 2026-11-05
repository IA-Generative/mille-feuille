"""Le modèle qui traite une demande.

Par défaut, le premier modèle de complétion de la table `llm_models` fait tout. Avec `LLM_AUTO_MODE`, une demande sans
modèle imposé est classée par difficulté (1 facile, 3 difficile) puis confiée au modèle le plus léger dont le niveau
suffit. Un modèle choisi explicitement (sur la conversation, l'analyse ou l'agent) l'emporte toujours. Sans modèle en
table, c'est `LLM_MODEL`, comme avant."""

import json
import logging
import time
from dataclasses import dataclass

from app.agent.runner import settings
from app.db import async_session_factory
from app.models.llm_model import MAX_LEVEL, MIN_LEVEL
from app.services import llm_models

logger = logging.getLogger(__name__)

# La table change rarement : lue au plus toutes les 30 secondes par process (et aussitôt après une modification).
CACHE_SECONDS = 30
# Quand la classification échoue : ni le plus léger (réponse faible), ni le plus coûteux.
DEFAULT_DIFFICULTY = 2
QUERY_CHARS = 2000

_CLASSIFY_PROMPT = (
    "Tu classes la difficulté d'une demande faite à un assistant qui travaille sur un dossier de documents. "
    'Réponds uniquement par un objet JSON : {"difficulty": 1, 2 ou 3}.\n'
    "1 : simple (salutation, question factuelle sur un champ précis, reformulation courte).\n"
    "2 : moyenne (recherche dans plusieurs passages, synthèse d'un document, comparaison simple).\n"
    "3 : difficile (raisonnement sur plusieurs documents, analyse juridique ou chiffrée, tâche en plusieurs étapes, "
    "rédaction longue)."
)


@dataclass(frozen=True)
class Choice:
    name: str
    level: int


_cache: tuple[float, list[Choice]] | None = None


def forget() -> None:
    """À appeler après une modification de la table : la prochaine demande la relit."""
    global _cache
    _cache = None


async def _models() -> list[Choice]:
    """Les modèles de complétion actifs, le préféré d'abord."""
    global _cache
    if _cache is not None and time.monotonic() - _cache[0] < CACHE_SECONDS:
        return _cache[1]
    try:
        async with async_session_factory() as db:
            models = [Choice(model.name, model.level) for model in await llm_models.completion_models(db)]
    except Exception:
        # Une table illisible ne doit pas empêcher de répondre : `LLM_MODEL`, sans mémoriser cet échec.
        logger.warning("Modèles LLM de la table illisibles : LLM_MODEL utilisé", exc_info=True)
        return []
    _cache = (time.monotonic(), models)
    return models


def pick(models: list[Choice], difficulty: int) -> str:
    """Le plus léger des modèles dont le niveau suffit (à niveau égal, le préféré) ; à défaut, le plus puissant."""
    difficulty = max(MIN_LEVEL, min(MAX_LEVEL, difficulty))
    able = [model for model in models if model.level >= difficulty]
    if able:
        return min(able, key=lambda model: model.level).name  # min garde le premier à niveau égal : le préféré
    return max(models, key=lambda model: model.level).name


async def default_model() -> str:
    """Le modèle de tout ce qui n'en choisit pas : le premier de la table, ou `LLM_MODEL` sans table."""
    models = await _models()
    return models[0].name if models else settings.LLM_MODEL


async def light_model() -> str:
    """Le modèle le plus léger, pour les petits travaux (planificateur, classification) : en mode auto seulement."""
    models = await _models()
    if not models:
        return settings.LLM_MODEL
    if not settings.LLM_AUTO_MODE:
        return models[0].name
    return min(models, key=lambda model: model.level).name


async def planner_model() -> str:
    return settings.CHAT_PLAN_MODEL or await light_model()


async def classify(query: str, models: list[Choice]) -> int:
    """La difficulté de la demande, jugée par le modèle le plus léger ; `DEFAULT_DIFFICULTY` si la réponse est
    inexploitable ou l'appel échoue."""
    from app.agent import llm  # import tardif : llm.py s'appuie sur ce module

    light = min(models, key=lambda model: model.level).name
    try:
        response = await llm.complete(
            model=light,
            messages=[
                {"role": "system", "content": _CLASSIFY_PROMPT},
                {"role": "user", "content": query[:QUERY_CHARS]},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=20,
        )
        difficulty = int(json.loads(response.choices[0].message.content or "{}")["difficulty"])
    except Exception:
        logger.warning("Difficulté de la demande non classée : niveau %d", DEFAULT_DIFFICULTY, exc_info=True)
        return DEFAULT_DIFFICULTY
    return max(MIN_LEVEL, min(MAX_LEVEL, difficulty))


async def for_query(query: str, *, explicit: str | None = None) -> str:
    """Le modèle d'une demande : celui qu'on a imposé, sinon (mode auto) celui que sa difficulté demande, sinon le
    modèle par défaut."""
    if explicit:
        return explicit
    models = await _models()
    if not models:
        return settings.LLM_MODEL
    if not settings.LLM_AUTO_MODE or len({model.level for model in models}) == 1 or not query.strip():
        return models[0].name
    difficulty = await classify(query, models)
    chosen = pick(models, difficulty)
    logger.info("Mode auto : difficulté %d, modèle %s", difficulty, chosen)
    return chosen


async def for_difficulty(difficulty: int, *, explicit: str | None = None) -> str:
    """Pour un travail dont la difficulté est connue d'avance (résumé, extraction) : pas de classification."""
    if explicit:
        return explicit
    models = await _models()
    if not models:
        return settings.LLM_MODEL
    return pick(models, difficulty) if settings.LLM_AUTO_MODE else models[0].name
