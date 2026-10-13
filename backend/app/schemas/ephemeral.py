import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.document_page import PredictionSource
from app.models.dossier import DossierStatus
from app.schemas.analyse import AgentCreate, AnalyseOut, EntityDefinitionIn, LabelDefinitionIn
from app.schemas.dossier import DossierOut


class EphemeralAnalyseCreate(BaseModel):
    name: str = Field(examples=["Analyse CNI + justificatif"])
    description: str = ""
    # False par défaut : purgée au TTL comme le reste de la ressource
    # éphémère. True = conservée indéfiniment, comme une Analyse classique.
    persist: bool = Field(
        default=False,
        description="False (défaut) : purgée automatiquement une fois son TTL écoulé, comme tout le reste de "
        "l'API éphémère. True : conservée indéfiniment, comme une Analyse classique de la plateforme.",
    )
    classification_prompt: str = ""
    multi_label: bool = Field(default=False, description="True : plusieurs labels possibles par page (sinon un seul).")
    labels: list[LabelDefinitionIn] = []
    extraction_prompt: str = ""
    entities: list[EntityDefinitionIn] = []
    agents: list[AgentCreate] = Field(
        default=[],
        description="Chaque agent est créé en une seule fois avec l'analyse - pas d'étape séparée "
        "contrairement au flux de création standard de la plateforme (POST /api/analyses puis PUT/POST par champ).",
    )

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Le nom ne peut pas être vide.")
        return value


class EphemeralAnalyseCreated(BaseModel):
    analyse_id: uuid.UUID = Field(description="À réutiliser tel quel dans le flux A (.../analyses/{id}/runs).")


class EphemeralAnalyseOut(AnalyseOut):
    """AnalyseOut + les métadonnées propres à l'analyse éphémère
    (analyse_ephemere) - expires_at suit le TTL du dernier run l'ayant
    utilisée (voir docs/ephemeral-api.md, section "Principe du TTL")."""

    persist: bool
    expires_at: datetime | None = Field(
        description="NULL tant qu'aucun run n'a référencé cette analyse et n'est arrivé à son terme, ou si "
        "persist=True. Sinon : date/heure de fin du dernier run terminé qui l'a utilisée, plus son ttl_hours."
    )


class EphemeralRunCreated(BaseModel):
    run_id: uuid.UUID = Field(description="À utiliser avec GET/POST .../stop/DELETE /api/ephemeral/runs/{id}.")


class EphemeralRunOut(DossierOut):
    """DossierOut + les métadonnées propres au run éphémère (dossier_ephemere)
    - expires_at reste `None` tant que le run n'a pas atteint un état
    terminal (voir docs/ephemeral-api.md, section "Principe du TTL")."""

    persist: bool
    ttl_hours: int | None = Field(description="Valeur effective utilisée pour ce run (défaut 24h, max 17520h).")
    expires_at: datetime | None = Field(
        description="NULL tant que le run est en_attente/en_cours (le TTL démarre à la fin de l'analyse, pas à "
        "la création), ou si persist=True. Sinon : ended_at + ttl_hours, figé une fois calculé."
    )


class EphemeralLabelResult(BaseModel):
    prediction_id: uuid.UUID = Field(description="À réutiliser dans POST /ephemeral/runs/{run_id}/feedback.")
    name: str
    confidence: float | None
    source: PredictionSource = Field(
        description="`textual` : texte de la page (OCR, VLM, LLM). `visual` : apparence de la page (CLIP). Chaque "
        "page reçoit les deux : une page peut avoir un label de chaque source."
    )


class EphemeralClassifiedPage(BaseModel):
    page_number: int
    labels: list[EphemeralLabelResult] = Field(
        description="Un seul label en mono-label ; un ou plusieurs en multi-label ; vide si la page n'a pas (encore) "
        "été classée."
    )


class EphemeralClassifiedDocument(BaseModel):
    name: str
    pages: list[EphemeralClassifiedPage]


class EphemeralClassificationOut(BaseModel):
    run_id: uuid.UUID
    status: DossierStatus
    error: str | None = Field(description="Message de l'étape en échec, si le run a échoué.")
    expires_at: datetime | None
    documents: list[EphemeralClassifiedDocument]


class EphemeralEntityResult(BaseModel):
    prediction_id: uuid.UUID = Field(description="À réutiliser dans POST /ephemeral/runs/{run_id}/feedback.")
    name: str
    value: str
    confidence: float | None
    source: PredictionSource = Field(
        description="`textual` : extraite par le LLM. `gliner` : extraite par GLiNER2.5 (modèle d'extraction sur le "
        "texte de la page). Chaque page reçoit les deux : une même entité peut apparaître avec chaque source."
    )
    pages: list[int] = Field(description="Toutes les pages sur lesquelles l'entité a été trouvée.")


class EphemeralExtractedPage(BaseModel):
    page_number: int
    entities: list[EphemeralEntityResult]


class EphemeralExtractedDocument(BaseModel):
    name: str
    pages: list[EphemeralExtractedPage]


class EphemeralExtractionOut(BaseModel):
    run_id: uuid.UUID
    status: DossierStatus
    error: str | None = Field(description="Message de l'étape en échec, si le run a échoué.")
    expires_at: datetime | None
    documents: list[EphemeralExtractedDocument]


class EphemeralRunSummary(BaseModel):
    """Une ligne de la liste des runs de l'appelant : de quoi les retrouver, pas leur contenu."""

    id: uuid.UUID
    kind: Literal["classification", "extraction", "analyse"] = Field(
        description="`classification` / `extraction` : run à une seule étape (flux C) ; `analyse` : pipeline complet."
    )
    status: DossierStatus
    documents: list[str] = Field(description="Noms des documents du run.")
    persist: bool
    created_at: datetime
    ended_at: datetime | None
    expires_at: datetime | None = Field(description="NULL si persist=True ou tant que le run n'est pas terminé.")
