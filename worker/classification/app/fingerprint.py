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


def classification_fingerprint(
    page: dict, label_definitions: list[dict], prompt: str, multi_label: bool = False
) -> str:
    """Une page classée : son texte, sa capture (clé S3), les labels, le prompt
    et les modèles (VLM pour la description d'image, LLM pour le choix)."""
    payload = {
        "unit": "classification",
        "pipeline": PIPELINE_VERSION,
        "text": text_hash(page.get("content")),
        "screenshot": page.get("screenshot_key"),
        "labels": _definitions(label_definitions),
        "prompt": prompt,
        "llm": settings.LLM_MODEL,
        "vlm": settings.VLM_MODEL,
    }
    if multi_label:
        # Seulement si vrai : l'empreinte des analyses mono-label existantes ne change pas.
        payload["multi_label"] = True
    return _digest(payload)
