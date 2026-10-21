"""Client OpenAI pour la classification : VLM (description de la capture d'une page) puis LLM (structured output)."""

import base64
import logging

from openai import OpenAI
from pydantic import BaseModel, Field

from app import usage
from app.config import settings

logger = logging.getLogger(__name__)


def _client() -> OpenAI:
    if not settings.is_configured:
        raise RuntimeError(
            "OPENAI_API_KEY et OPENAI_API_BASE_URL doivent être configurés pour utiliser le worker classification."
        )
    return OpenAI(
        api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_API_BASE_URL, http_client=usage.http_client()
    )


class LabelPrediction(BaseModel):
    """Résultat de classification pour une page : un label parmi ceux
    définis dans l'analyse, avec un niveau de confiance."""

    label_name: str = Field(description="Nom exact du label choisi parmi les définitions fournies")
    confidence: float = Field(description="Score de confiance entre 0 et 1", ge=0.0, le=1.0)
    reasoning: str = Field(default="", description="Brève justification du choix (optionnel)")


class ClassificationResult(BaseModel):
    """Résultat de classification pour une page : un seul label (la
    classification est mono-label par page)."""

    prediction: LabelPrediction


class MultiLabelClassificationResult(BaseModel):
    """Résultat de classification multi-label : un ou plusieurs labels pour la page."""

    predictions: list[LabelPrediction] = Field(
        description="Tous les labels qui s'appliquent à la page (au moins un), sans doublon"
    )


_VLM_PROMPT = (
    "Décris cette page de document de manière structurée et factuelle. "
    "Identifie : le type de document (CNI, passeport, facture, contrat...), "
    "les éléments visibles (titres, tableaux, signatures, tampons, photos), "
    "et toute information pertinente pour sa classification. "
    "Sois concis mais précis."
)


def describe_page_image(image_bytes: bytes) -> str:
    """Demande au VLM de décrire la capture d'une page. Le texte renvoyé
    est combiné avec le texte OCR de la page pour alimenter la
    classification (le LLM texte a ainsi à la fois le contenu lu et ce que
    le VLM a vu)."""
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    response = _client().chat.completions.create(
        model=settings.VLM_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _VLM_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }
        ],
        max_tokens=500,
        temperature=0.1,
    )
    return response.choices[0].message.content or ""


def source_section(source: dict | None) -> str:
    """D'où vient le document (nom + description de sa source), en contexte pour le LLM ; vide sans source."""
    if not source or not source.get("name"):
        return ""
    description = (source.get("description") or "").strip()
    detail = f" : {description}" if description else ""
    return f"--- Source du document ---\n{source['name']}{detail}\n\n"


def classify_page(
    *,
    page_text: str,
    image_description: str,
    label_definitions: list[dict],
    classification_prompt: str,
    multi_label: bool = False,
    source: dict | None = None,
) -> ClassificationResult | MultiLabelClassificationResult:
    """Classifie une page en utilisant le texte OCR + la description VLM.
    Renvoie un résultat structuré garantissant que le ou les labels choisis
    existent parmi les définitions fournies : ClassificationResult (un seul
    label) ou, si `multi_label`, MultiLabelClassificationResult."""
    labels_desc = "\n".join(f"- {label['name']}: {label['definition']}" for label in label_definitions)
    choice = (
        "Choisis TOUS les labels qui s'appliquent à la page (au moins un)" if multi_label else "Choisis UN seul label"
    )
    system = (
        f"{classification_prompt}\n\n"
        f"Tu es un assistant de classification documentaire. "
        f"{choice} parmi les suivants :\n{labels_desc}\n\n"
        f"Réponds uniquement avec le JSON demandé."
    )
    user = (
        f"{source_section(source)}"
        f"--- Texte extrait de la page (OCR) ---\n{page_text or '(vide)'}\n\n"
        f"--- Description visuelle de la page (VLM) ---\n{image_description or '(indisponible)'}\n\n"
        f"{'Quels labels correspondent' if multi_label else 'Quel label correspond le mieux'} à cette page ?"
    )
    response = _client().beta.chat.completions.parse(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format=MultiLabelClassificationResult if multi_label else ClassificationResult,
        temperature=0.1,
    )
    return response.choices[0].message.parsed
