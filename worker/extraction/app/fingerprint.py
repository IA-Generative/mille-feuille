"""Empreinte d'entrées d'une unité de calcul (issue #126, parent #113).

Un hash de **tout ce qui détermine le résultat** d'une unité : texte lu, définitions, prompt et modèles. Deux
unités aux entrées identiques ont la même empreinte, ce qui permet à la relance incrémentale (#119) de ne pas
recalculer ce qui n'a pas changé. Elle ne dépend ni de la valeur du résultat, ni des identifiants d'exécution.
"""

import hashlib
import json
from typing import Any

from app.config import settings

# À incrémenter quand la logique d'une étape change de façon à modifier ses résultats : toutes les empreintes
# changent, rien n'est repris à tort d'une exécution précédente.
PIPELINE_VERSION = "pipeline-1"


def text_hash(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _digest(payload: dict[str, Any]) -> str:
    # Forme canonique : clés triées, pas d'espaces, caractères non échappés.
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _definitions(definitions: list[dict]) -> list[dict]:
    # L'ordre est conservé : il est celui de l'analyse (et des groupes).
    return [
        {"id": d.get("id"), "name": d.get("name"), "type": d.get("type"), "definition": d.get("definition")}
        for d in definitions
    ]


def gliner_extraction_fingerprint(pages: list[dict], entity_definitions: list[dict]) -> str:
    """Un document passé dans GLiNER : le texte de chaque page (dans l'ordre), les définitions et le modèle.
    Ni prompt ni LLM : GLiNER ne les voit pas."""
    return _digest(
        {
            "unit": "extraction_gliner",
            "pipeline": PIPELINE_VERSION,
            "pages": [{"number": p["page_number"], "text": text_hash(p.get("content"))} for p in pages],
            "entities": _definitions(entity_definitions),
            "gliner": settings.GLINER_MODEL,
            "threshold": settings.GLINER_THRESHOLD,
        }
    )


def extraction_fingerprint(
    pages: list[dict], entity_definitions: list[dict], prompt: str, source: dict | None = None
) -> str:
    """Un lot de pages × un groupe de définitions : le texte de chaque page (dans l'ordre), les définitions du
    groupe, le prompt, la source du document (si elle en a une : le LLM la reçoit en contexte) et le modèle."""
    payload = {
        "unit": "extraction",
        "pipeline": PIPELINE_VERSION,
        "pages": [{"number": p["page_number"], "text": text_hash(p.get("content"))} for p in pages],
        "entities": _definitions(entity_definitions),
        "prompt": prompt,
        "llm": settings.LLM_MODEL,
    }
    if source:
        # Seulement si le document a une source : l'empreinte des documents sans source ne change pas.
        payload["source"] = {"name": source.get("name"), "description": source.get("description")}
    return _digest(payload)
