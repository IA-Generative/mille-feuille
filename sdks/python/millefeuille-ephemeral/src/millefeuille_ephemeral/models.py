"""Modèles de l'API éphémère (alignés sur backend/app/schemas/ephemeral.py).

Réutilise les modèles du SDK standard ; voir `millefeuille.models` pour les règles d'entrée/sortie.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from millefeuille.models import (
    AgentCreate,
    Analyse,
    Dossier,
    EntityDefinitionIn,
    LabelDefinitionIn,
    _In,
    _Out,
)
from pydantic import field_validator

TTL_DEFAULT_HOURS = 24
TTL_MAX_HOURS = 17520  # 2 ans

# Ancien nom, conservé pour la lisibilité côté appelant.
AgentDefinition = AgentCreate


class EphemeralAnalysisConfig(_In):
    """Définition complète d'une analyse éphémère, créée en un seul appel (`POST /ephemeral/analyses`).

    Les listes acceptent les modèles typés (`LabelDefinitionIn`, `EntityDefinitionIn`, `AgentCreate`)
    ou des dicts équivalents, validés à la construction.
    """

    name: str
    description: str = ""
    # False : purgée automatiquement au TTL de son dernier run. True : conservée indéfiniment.
    persist: bool = False
    classification_prompt: str = ""
    # False (défaut) : un seul label par page ; True : un ou plusieurs.
    multi_label: bool = False
    labels: list[LabelDefinitionIn] = []
    extraction_prompt: str = ""
    entities: list[EntityDefinitionIn] = []
    agents: list[AgentCreate] = []

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Le nom ne peut pas être vide.")
        return value


class EphemeralAnalyseCreated(_Out):
    analyse_id: uuid.UUID


class EphemeralRunCreated(_Out):
    run_id: uuid.UUID


class EphemeralAnalyse(Analyse):
    """Analyse + TTL. `expires_at` : `None` si `persist`, ou tant qu'aucun run n'a fini."""

    persist: bool
    expires_at: datetime | None


class EphemeralRun(Dossier):
    """Run éphémère. `expires_at` = fin du run + `ttl_hours`, `None` tant qu'il n'est pas terminé."""

    persist: bool
    ttl_hours: int | None
    expires_at: datetime | None
