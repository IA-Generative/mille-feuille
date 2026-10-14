"""Client OpenAI pour l'extraction d'entités : LLM en structured output (JSON schema via response_format)."""

import logging

from openai import OpenAI
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)


def _client() -> OpenAI:
    if not settings.is_configured:
        raise RuntimeError(
            "OPENAI_API_KEY et OPENAI_API_BASE_URL doivent être configurés pour utiliser le worker extraction."
        )
    return OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_API_BASE_URL)


class EntityValue(BaseModel):
    """Une entité extraite d'une ou plusieurs pages."""

    entity_name: str = Field(description="Nom exact de l'entité parmi les définitions fournies")
    value: str = Field(description="Valeur extraite pour cette entité")
    confidence: float = Field(description="Score de confiance entre 0 et 1", ge=0.0, le=1.0)
    page_numbers: list[int] = Field(
        default_factory=list,
        description="Numéros des pages (1-indexed) où cette entité apparaît",
    )
    reasoning: str = Field(default="", description="Brève justification (optionnel)")


class ExtractionResult(BaseModel):
    """Résultat d'extraction d'entités pour un batch de pages."""

    entities: list[EntityValue] = Field(default_factory=list, description="Entités extraites du batch")


def source_section(source: dict | None) -> str:
    """D'où vient le document (nom + description de sa source), en contexte pour le LLM ; vide sans source."""
    if not source or not source.get("name"):
        return ""
    description = (source.get("description") or "").strip()
    detail = f" : {description}" if description else ""
    return f"--- Source du document ---\n{source['name']}{detail}\n\n"


def extract_entities_batch(
    *,
    pages: list[dict],
    entity_definitions: list[dict],
    extraction_prompt: str,
    source: dict | None = None,
) -> ExtractionResult:
    """Extrait les entités d'un batch de pages. Chaque page est un dict avec
    `page_number` et `content`. `source` : d'où vient le document, donnée en contexte. Renvoie un résultat structuré
    (ExtractionResult) garantissant que chaque entité extraite correspond à
    une définition fournie."""
    entities_desc = "\n".join(
        f"- {entity['name']} (type: {entity['type']}): {entity['definition']}" for entity in entity_definitions
    )
    system = (
        f"{extraction_prompt}\n\n"
        f"Tu es un assistant d'extraction d'entités. "
        f"Extrais les valeurs pour les entités suivantes :\n{entities_desc}\n\n"
        f"Pour chaque entité trouvée, indique sur quelles pages (par numéro) "
        f"elle apparaît. Si une entité n'est pas présente, ne l'inclus pas. "
        f"Réponds uniquement avec le JSON demandé."
    )
    pages_text = "\n\n".join(f"--- Page {page['page_number']} ---\n{page['content'] or '(vide)'}" for page in pages)
    response = _client().beta.chat.completions.parse(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"{source_section(source)}{pages_text}"},
        ],
        response_format=ExtractionResult,
        temperature=0.1,
    )
    return response.choices[0].message.parsed
