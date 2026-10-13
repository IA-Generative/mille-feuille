import logging
from dataclasses import dataclass, field

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def get_client() -> httpx.Client:
    """Client HTTP authentifié vers le BFF, pour tous les appels à
    /api/internal/* (logs d'exécution, prédictions déposées, définitions
    de l'analyse...). Le jeton (voir app.core.security.internal.verify_app_token
    côté backend) est soit le secret de bootstrap fixe (dev local, docker-
    compose), soit le jeton en clair d'un AppToken créé via
    POST /api/app-tokens (prod, révocable indépendamment) - les deux
    marchent avec la même variable d'environnement, sans changement de
    code ici."""
    return httpx.Client(
        base_url=f"{settings.BACKEND_INTERNAL_URL}/api/internal",
        headers={"X-App-Token": settings.INTERNAL_WORKER_TOKEN},
        timeout=60.0,
    )


def add_execution_log(client: httpx.Client, step_id: str, *, level: str = "info", message: str) -> dict:
    response = client.post(f"/execution-steps/{step_id}/logs", json={"level": level, "message": message})
    response.raise_for_status()
    return response.json()


def complete_execution_step(client: httpx.Client, step_id: str, *, status: str, output: str | None = None) -> dict:
    response = client.post(
        f"/execution-steps/{step_id}/complete",
        json={"status": status, "output": output},
    )
    response.raise_for_status()
    return response.json()


def get_dossier(client: httpx.Client, dossier_id: str) -> dict:
    """Récupère le dossier avec ses documents, pages, et étapes d'exécution.
    Nécessite GET /internal/dossiers/{dossier_id} côté backend."""
    response = client.get(f"/dossiers/{dossier_id}")
    response.raise_for_status()
    return response.json()


def get_analyse_definitions(client: httpx.Client, analyse_id: str) -> dict:
    """Récupère les définitions de labels et d'entités de l'analyse, ainsi
    que les prompts de classification et d'extraction. Nécessite
    GET /internal/analyses/{analyse_id} côté backend."""
    response = client.get(f"/analyses/{analyse_id}")
    response.raise_for_status()
    return response.json()


def add_prediction(
    client: httpx.Client,
    page_id: str,
    *,
    kind: str,
    name: str,
    value: str,
    confidence: float | None = None,
    source: str = "textual",
    label_definition_id: str | None = None,
    entity_definition_id: str | None = None,
    page_ids: list[str] | None = None,
    bounding_box_ids: list[str] | None = None,
    unit_id: str | None = None,
) -> dict:
    body = {
        "kind": kind,
        "name": name,
        "value": value,
        "confidence": confidence,
        "source": source,
        "label_definition_id": label_definition_id,
        "entity_definition_id": entity_definition_id,
        "page_ids": page_ids or [],
        "bounding_box_ids": bounding_box_ids or [],
    }
    # Unité de calcul de l'analyse de dossier (voir declare_unit) : le
    # backend en déduit l'élément d'analyse correspondant à la prédiction.
    if unit_id is not None:
        body["unit_id"] = unit_id
    response = client.post(f"/pages/{page_id}/predictions", json=body)
    response.raise_for_status()
    return response.json()


@dataclass
class DeclaredUnit:
    """Unité déclarée au backend. ``reused`` : elle a été reprise de l'analyse
    précédente (même empreinte, relance incrémentale #119) : ses éléments sont déjà
    copiés, il ne faut **pas** la calculer. ``entities`` : entités reprises (nom de la
    définition, valeur du modèle), pour amorcer la fusion des doublons entre lots."""

    id: str
    reused: bool = False
    entities: list[tuple[str, str]] = field(default_factory=list)


def declare_unit(
    client: httpx.Client, dossier_id: str, kind: str, description: dict, fingerprint: str | None = None
) -> DeclaredUnit | None:
    """Déclare une unité de calcul (page, lot de pages...) avec l'empreinte de ses
    entrées (voir app.fingerprint). Renvoie l'unité (éventuellement reprise de
    l'analyse précédente), ou None si elle n'a pas pu être déclarée."""
    try:
        body = {"kind": kind, "description": description}
        if fingerprint is not None:
            body["input_fingerprint"] = fingerprint
        response = client.post(f"/dossiers/{dossier_id}/analysis-units", json=body)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        return DeclaredUnit(
            id=data["id"],
            reused=bool(data.get("reused", False)),
            entities=[(e["name"], e["value"]) for e in data.get("reused_entities", [])],
        )
    except Exception:
        logger.warning("Could not declare %s unit for dossier %s", kind, dossier_id, exc_info=True)
        return None


def complete_unit(client: httpx.Client, unit_id: str | None, status: str) -> None:
    """Marque une unité terminée ou en échec (sans effet si elle n'existe pas)."""
    if unit_id is None:
        return
    try:
        client.post(f"/analysis-units/{unit_id}/complete", json={"status": status}).raise_for_status()
    except Exception:
        logger.warning("Could not complete unit %s", unit_id, exc_info=True)
