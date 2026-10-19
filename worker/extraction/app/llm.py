"""Client OpenAI pour l'extraction d'entités : LLM en structured output (JSON schema via response_format)."""

import json
import logging

from openai import LengthFinishReasonError, OpenAI
from pydantic import BaseModel, Field, ValidationError

from app.config import settings

logger = logging.getLogger(__name__)


def _client() -> OpenAI:
    if not settings.is_configured:
        raise RuntimeError(
            "OPENAI_API_KEY et OPENAI_API_BASE_URL doivent être configurés pour utiliser le worker extraction."
        )
    # Délai et nouvelles tentatives explicites : sans eux, le SDK attend 600 s par appel (voir WorkerSettings).
    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_API_BASE_URL,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )


_TEMPERATURE = 0.1


def _avec_schema_dans_le_prompt(messages: list[dict], modele: type[BaseModel]) -> list[dict]:
    """Les mêmes messages, le schéma JSON attendu ajouté à la consigne système (gemma n'accepte qu'un
    seul message système, en tête : on complète le premier plutôt que d'en ajouter un)."""
    consigne = "Réponds avec un seul objet JSON conforme à ce schéma JSON, sans autre texte :\n" + json.dumps(
        modele.model_json_schema(), ensure_ascii=False
    )
    copie = [dict(m) for m in messages]
    if copie and copie[0].get("role") == "system":
        copie[0]["content"] = f"{copie[0]['content']}\n\n{consigne}"
    else:
        copie.insert(0, {"role": "system", "content": consigne})
    return copie


def _completion_structuree[T: BaseModel](modele: type[T], messages: list[dict], *, max_tokens: int) -> T:
    """Sortie structurée en deux temps.

    1. Schéma imposé au décodage (`response_format=modele`), borné par `max_tokens`. Sur le hub, gemma-4 en
       décodage guidé part parfois en boucle d'espaces à l'intérieur du JSON (observé le 19/10/2026 : des
       centaines de jetons de tabulations, puis jusqu'à la limite du contexte, soit des minutes sans réponse
       et une étape en échec). La borne transforme cette boucle en réponse tronquée, immédiate.
    2. Repli : mode `json_object`, le schéma décrit dans le prompt, la réponse validée par pydantic. Sur le
       même prompt, ce mode répond en moins d'une seconde avec la forme attendue.
    """
    client = _client()
    try:
        response = client.beta.chat.completions.parse(
            model=settings.LLM_MODEL,
            messages=messages,
            response_format=modele,
            temperature=_TEMPERATURE,
            max_tokens=max_tokens,
        )
        parsed = response.choices[0].message.parsed
        if parsed is not None:
            return parsed
        logger.warning(
            "Sortie structurée vide (finish_reason=%s) : repli en json_object", response.choices[0].finish_reason
        )
    except (LengthFinishReasonError, ValidationError, ValueError) as exc:
        logger.warning("Sortie structurée inexploitable (%s) : repli en json_object", type(exc).__name__)
    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=_avec_schema_dans_le_prompt(messages, modele),
        response_format={"type": "json_object"},
        temperature=_TEMPERATURE,
        max_tokens=max_tokens,
    )
    return modele.model_validate_json(response.choices[0].message.content or "")


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
    # La part du budget réservée à la réponse borne aussi la génération : voir _completion_structuree.
    return _completion_structuree(
        ExtractionResult,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"{source_section(source)}{pages_text}"},
        ],
        max_tokens=settings.EXTRACTION_RESERVED_OUTPUT_TOKENS,
    )
