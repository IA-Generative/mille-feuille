"""Modèles de l'API éphémère (alignés sur backend/app/schemas/ephemeral.py).

Réutilise les modèles du SDK standard ; voir `millefeuille.models` pour les règles d'entrée/sortie.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from millefeuille.models import (
    AgentCreate,
    Analyse,
    Dossier,
    DossierStatus,
    EntityDefinitionIn,
    LabelDefinitionIn,
    PredictionSource,
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


class EphemeralRunSummary(_Out):
    """Une ligne de la liste des runs de l'appelant : de quoi les retrouver, pas leur contenu."""

    id: uuid.UUID
    # `classification` / `extraction` : run à une seule étape (un document) ; `analyse` : pipeline complet.
    kind: Literal["classification", "extraction", "analyse"]
    status: DossierStatus
    documents: list[str]
    persist: bool
    created_at: datetime
    ended_at: datetime | None
    # None si `persist` ou tant que le run n'est pas terminé.
    expires_at: datetime | None


class _OneShotRun(_Out):
    """Base des résultats d'un run à une seule étape (un document) : classification ou extraction."""

    run_id: uuid.UUID
    status: DossierStatus
    # Message de l'étape en échec, si le run a échoué.
    error: str | None
    expires_at: datetime | None


class EphemeralLabelResult(_Out):
    name: str
    confidence: float | None
    # `textual` : texte de la page (OCR, VLM, LLM) ; `visual` : apparence de la capture (CLIP). Chaque page reçoit
    # les deux.
    source: PredictionSource
    prediction_id: uuid.UUID


class EphemeralClassifiedPage(_Out):
    page_number: int
    # Textuels d'abord, puis visuels, chacun par confiance décroissante ; vide si la page n'est pas (encore) classée.
    labels: list[EphemeralLabelResult]


class EphemeralClassifiedDocument(_Out):
    name: str
    pages: list[EphemeralClassifiedPage]


class EphemeralClassification(_OneShotRun):
    """Résultat d'une classification : le ou les labels de chaque page de chaque document."""

    documents: list[EphemeralClassifiedDocument]


class EphemeralEntityResult(_Out):
    name: str
    value: str
    confidence: float | None
    # `textual` : extraite par le LLM ; `gliner` : extraite par GLiNER2.5. La même valeur peut apparaître avec chaque
    # source.
    source: PredictionSource
    # Toutes les pages sur lesquelles l'entité a été trouvée.
    pages: list[int]
    prediction_id: uuid.UUID


class EphemeralExtractedPage(_Out):
    page_number: int
    entities: list[EphemeralEntityResult]


class EphemeralExtractedDocument(_Out):
    name: str
    pages: list[EphemeralExtractedPage]


class EphemeralExtraction(_OneShotRun):
    """Résultat d'une extraction : les entités de chaque page de chaque document."""

    documents: list[EphemeralExtractedDocument]
