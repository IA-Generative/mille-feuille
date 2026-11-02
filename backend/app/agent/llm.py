"""Client OpenAI (LLM texte, structured output) de l'agent : propositions depuis une note, champs de document,
résumés, suggestions d'analyses. Chaque appel déclare sa consommation (voir usage.py)."""

import logging

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.agent import usage
from app.agent.document_generation import GeneratedFields
from app.agent.runner import settings
from app.config import LlmSettings

logger = logging.getLogger(__name__)

_llm_settings = LlmSettings()
_client_instance: AsyncOpenAI | None = None


def client() -> AsyncOpenAI:
    global _client_instance
    if not _llm_settings.is_configured:
        raise RuntimeError("OPENAI_API_KEY et OPENAI_API_BASE_URL doivent être configurés pour utiliser l'agent.")
    if _client_instance is None:
        _client_instance = AsyncOpenAI(
            api_key=_llm_settings.OPENAI_API_KEY, base_url=_llm_settings.OPENAI_API_BASE_URL, timeout=600.0
        )
    return _client_instance


async def complete(**kwargs):  # noqa: ANN003, ANN201
    """`chat.completions.create` + déclaration de la consommation."""
    response = await client().chat.completions.create(**kwargs)
    await usage.record(response.model, response.usage)
    return response


async def parse(**kwargs):  # noqa: ANN003, ANN201
    """`beta.chat.completions.parse` (structured output) + déclaration de la consommation."""
    response = await client().beta.chat.completions.parse(**kwargs)
    await usage.record(response.model, response.usage)
    return response


# ---------------------------------------------------------------------------
# LLM : valeurs des champs d'un document (issue #141)
# ---------------------------------------------------------------------------


async def generate_field_values(messages: list[dict[str, str]]) -> GeneratedFields:
    """Demande au LLM une valeur par champ (structured output). Les messages sont construits par
    ``app.agent.document_generation`` (prompt versionné + garde-fous, contexte borné) ; la réponse est ensuite
    filtrée : seuls les champs demandés, avec des sources connues, sont retenus."""
    response = await parse(
        model=settings.LLM_MODEL, messages=messages, response_format=GeneratedFields, temperature=0.1
    )
    return response.choices[0].message.parsed or GeneratedFields()


# ---------------------------------------------------------------------------
# LLM : résumé de texte (issue #52)
# ---------------------------------------------------------------------------

_SUMMARY_SYSTEM_PROMPT = (
    "Tu es un assistant de synthèse documentaire. "
    "Résume le texte fourni en français, de manière concise et factuelle. "
    "Identifie les informations clés : type de document, parties prenantes, "
    "dates importantes, montants, et tout élément pertinent. "
    "Le résumé doit faire 3 à 5 phrases maximum, sans introduction ni conclusion superflue."
)


async def summarize_text(content: str, *, max_tokens: int = 500) -> str:
    """Génère un résumé concis du texte fourni via le LLM. Utilisé pour les résumés de documents (concaténation
    des pages) et les résumés de dossier (concaténation des résumés individuels + synthèses d'agents)."""
    if not content or not content.strip():
        return ""
    response = await complete(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        max_tokens=max_tokens,
        temperature=0.1,
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# LLM : suggestion d'analyse pour dossier « à ranger » (issue #54)
# ---------------------------------------------------------------------------


class AnalyseSuggestion(BaseModel):
    """Une analyse candidate pour un dossier « à ranger », avec un score de pertinence et une justification."""

    analyse_id: str = Field(description="Identifiant UUID de l'analyse")
    score: float = Field(description="Score de pertinence entre 0 et 1", ge=0.0, le=1.0)
    rationale: str = Field(description="Brève justification du score (1-2 phrases)")


class SuggestionResult(BaseModel):
    """Résultat de la suggestion d'analyse : liste triée par pertinence décroissante."""

    suggestions: list[AnalyseSuggestion] = Field(
        description="Liste des analyses candidates, triées par score décroissant"
    )


_SUGGESTION_SYSTEM_PROMPT = (
    "Tu es un assistant de classification documentaire. "
    "On te fournit le résumé d'un dossier (ensemble de documents) et la liste "
    "des analyses disponibles (chacune avec son nom et sa description). "
    "Ton rôle est d'identifier quelles analyses sont les plus pertinentes "
    "pour ce dossier, en justifiant ton choix. "
    "Réponds uniquement avec le JSON demandé."
)


async def suggest_analyses(*, dossier_summary: str, analyses: list[dict]) -> SuggestionResult:
    """Demande au LLM de classer les analyses disponibles par pertinence pour un dossier « à ranger ». Chaque
    analyse est un dict avec `id`, `name`, et `description`."""
    if not analyses:
        return SuggestionResult(suggestions=[])

    analyses_desc = "\n".join(
        f"- ID: {a['id']} | Nom: {a['name']} | Description: {a.get('description') or '(aucune)'}" for a in analyses
    )
    user_content = (
        f"## Résumé du dossier\n\n{dossier_summary or '(dossier sans contenu)'}\n\n"
        f"## Analyses disponibles\n\n{analyses_desc}\n\n"
        f"Quelles analyses sont les plus pertinentes pour ce dossier ? "
        f"Donne un score entre 0 et 1 pour chaque analyse, avec une brève "
        f"justification. Trie par score décroissant."
    )
    response = await parse(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": _SUGGESTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format=SuggestionResult,
        temperature=0.1,
    )
    return response.choices[0].message.parsed or SuggestionResult(suggestions=[])
