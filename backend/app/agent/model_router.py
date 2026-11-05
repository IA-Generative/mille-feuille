"""Le modèle qui traite une demande.

Par défaut, le premier modèle actif de la table `llm_models` fait tout. En mode auto (réglage de l'administrateur), une
demande sans modèle imposé est analysée par le modèle par défaut : à partir des **capacités** que l'administrateur a
définies (nom et description), il dit lesquelles la demande demande. Le premier modèle, dans l'ordre de la liste, qui
les a toutes répond. Un modèle choisi explicitement (sur la conversation, l'analyse ou l'agent) l'emporte toujours.
Sans modèle en table, c'est `LLM_MODEL`, comme avant."""

import json
import logging
import time
from dataclasses import dataclass

from app.agent.runner import settings
from app.db import async_session_factory
from app.services import llm_models

logger = logging.getLogger(__name__)

# La table change rarement : lue au plus toutes les 30 secondes par process (et aussitôt après une modification).
CACHE_SECONDS = 30
QUERY_CHARS = 2000

_CLASSIFY_PROMPT = (
    "Tu choisis les capacités dont a besoin un modèle pour traiter une demande faite à un assistant qui travaille sur "
    "un dossier de documents. Voici les capacités possibles, avec ce qu'elles permettent :\n{capabilities}\n\n"
    'Réponds uniquement par un objet JSON : {{"capabilities": ["nom", ...]}}, avec les noms exacts des capacités '
    "nécessaires. Une demande simple n'en demande aucune : réponds alors une liste vide."
)


@dataclass(frozen=True)
class Capability:
    id: str
    name: str
    description: str


@dataclass(frozen=True)
class Choice:
    name: str
    capability_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Catalogue:
    models: list[Choice]
    capabilities: list[Capability]
    auto: bool


_cache: tuple[float, Catalogue] | None = None


def forget() -> None:
    """À appeler après une modification de la table : la prochaine demande la relit."""
    global _cache
    _cache = None


async def _catalogue() -> Catalogue:
    global _cache
    if _cache is not None and time.monotonic() - _cache[0] < CACHE_SECONDS:
        return _cache[1]
    try:
        async with async_session_factory() as db:
            models = [
                Choice(model.name, frozenset(str(capability.id) for capability in model.capabilities))
                for model in await llm_models.enabled_models(db)
            ]
            capabilities = [
                Capability(str(capability.id), capability.name, capability.description)
                for capability in await llm_models.list_capabilities(db)
            ]
            auto = await llm_models.auto_mode(db)
    except Exception:
        # Une table illisible ne doit pas empêcher de répondre : `LLM_MODEL`, sans mémoriser cet échec.
        logger.warning("Modèles LLM de la table illisibles : LLM_MODEL utilisé", exc_info=True)
        return Catalogue([], [], False)
    catalogue = Catalogue(models, capabilities, auto)
    _cache = (time.monotonic(), catalogue)
    return catalogue


def pick(models: list[Choice], required: set[str]) -> str:
    """Le premier modèle (dans l'ordre de la liste) qui a toutes les capacités demandées ; à défaut, celui qui en a le
    plus (le premier à égalité). Sans capacité demandée, le premier."""
    if not required:
        return models[0].name
    for model in models:
        if required <= model.capability_ids:
            return model.name
    return max(models, key=lambda model: len(required & model.capability_ids)).name


async def default_model() -> str:
    """Le modèle de tout ce qui n'en choisit pas : le premier actif de la table, ou `LLM_MODEL` sans table."""
    catalogue = await _catalogue()
    return catalogue.models[0].name if catalogue.models else settings.LLM_MODEL


async def registered_default() -> str | None:
    """Le premier modèle actif de la table, ou None quand l'administrateur n'en a enregistré aucun."""
    catalogue = await _catalogue()
    return catalogue.models[0].name if catalogue.models else None


async def planner_model() -> str:
    return settings.CHAT_PLAN_MODEL or await default_model()


async def classify(query: str, catalogue: Catalogue) -> set[str]:
    """Les capacités que la demande demande, jugées par le modèle par défaut ; aucune si la réponse est inexploitable
    ou si l'appel échoue (le premier modèle répond alors)."""
    from app.agent import llm  # import tardif : llm.py s'appuie sur ce module

    listed = "\n".join(f"- {capability.name} : {capability.description}" for capability in catalogue.capabilities)
    try:
        response = await llm.complete(
            model=catalogue.models[0].name,
            messages=[
                {"role": "system", "content": _CLASSIFY_PROMPT.format(capabilities=listed)},
                {"role": "user", "content": query[:QUERY_CHARS]},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=100,
        )
        names = json.loads(response.choices[0].message.content or "{}")["capabilities"]
    except Exception:
        logger.warning("Capacités de la demande non classées : premier modèle", exc_info=True)
        return set()
    by_name = {capability.name.casefold(): capability.id for capability in catalogue.capabilities}
    return {by_name[name.casefold()] for name in names if isinstance(name, str) and name.casefold() in by_name}


async def for_query(query: str, *, explicit: str | None = None) -> str:
    """Le modèle d'une demande : celui qu'on a imposé, sinon (mode auto) celui que ses capacités demandent, sinon le
    modèle par défaut."""
    if explicit:
        return explicit
    catalogue = await _catalogue()
    if not catalogue.models:
        return settings.LLM_MODEL
    if not catalogue.auto or not catalogue.capabilities or len(catalogue.models) == 1 or not query.strip():
        return catalogue.models[0].name
    required = await classify(query, catalogue)
    chosen = pick(catalogue.models, required)
    logger.info("Mode auto : %d capacité(s) demandée(s), modèle %s", len(required), chosen)
    return chosen
