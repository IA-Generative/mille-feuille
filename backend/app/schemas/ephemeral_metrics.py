import uuid

from pydantic import BaseModel, Field, model_validator

from app.models.document_page import PredictionKind, PredictionSource
from app.models.ephemeral_feedback import EphemeralVerdict

MAX_VERDICTS_PER_CALL = 500


class FeedbackItemIn(BaseModel):
    prediction_id: uuid.UUID = Field(
        description="`prediction_id` d'un label (GET .../classifications/{run_id}) ou d'une entité "
        "(GET .../extractions/{run_id}, ou `predictions[].id` de GET .../runs/{run_id})."
    )
    verdict: EphemeralVerdict
    expected_name: str | None = Field(
        default=None,
        description="Pour un label jugé `incorrect` : le nom du label qui était attendu (matrice de confusion).",
    )

    @model_validator(mode="after")
    def _expected_name_only_for_incorrect(self) -> "FeedbackItemIn":
        if self.expected_name is not None and self.verdict != EphemeralVerdict.INCORRECT:
            raise ValueError("`expected_name` n'a de sens que pour un verdict `incorrect`.")
        return self


class FeedbackIn(BaseModel):
    items: list[FeedbackItemIn] = Field(min_length=1, max_length=MAX_VERDICTS_PER_CALL)


class FeedbackOut(BaseModel):
    prediction_id: uuid.UUID
    kind: PredictionKind
    name: str
    source: PredictionSource
    page_number: int
    confidence: float | None
    verdict: EphemeralVerdict
    expected_name: str | None


class QualityOut(BaseModel):
    """Part des prédictions jugées bonnes, parmi celles qui ont reçu un verdict."""

    evaluated: int
    correct: int
    incorrect: int
    precision: float | None = Field(description="correct / evaluated ; null si aucun verdict.")
    avg_confidence_correct: float | None
    avg_confidence_incorrect: float | None


class SourceQualityOut(QualityOut):
    kind: PredictionKind
    source: PredictionSource


class NameQualityOut(QualityOut):
    kind: PredictionKind
    source: PredictionSource
    name: str


class ConfusionOut(BaseModel):
    source: PredictionSource
    predicted: str
    expected: str
    count: int


class StepMetricsOut(BaseModel):
    kind: str
    status: str
    duration_seconds: float | None


class VolumeOut(BaseModel):
    """Ce qu'une méthode a produit, sans regarder si c'est juste."""

    kind: PredictionKind
    source: PredictionSource
    predictions: int
    pages: int = Field(description="Pages ayant au moins une prédiction de cette méthode.")
    avg_confidence: float | None
    min_confidence: float | None
    max_confidence: float | None


class NameVolumeOut(BaseModel):
    kind: PredictionKind
    source: PredictionSource
    name: str
    predictions: int
    avg_confidence: float | None


class AgreementOut(BaseModel):
    """Accord entre la classification textuelle et la classification visuelle, page par page : sans vérité terrain,
    c'est un indicateur de fiabilité (deux méthodes indépendantes qui s'accordent sont plus sûres)."""

    pages_compared: int = Field(description="Pages qui ont des labels des deux sources.")
    pages_agreeing: int = Field(description="Pages dont l'ensemble de labels est identique pour les deux sources.")
    agreement_rate: float | None


class RunMetricsOut(BaseModel):
    run_id: uuid.UUID
    status: str
    document_count: int
    page_count: int
    duration_seconds: float | None
    steps: list[StepMetricsOut]
    volume: list[VolumeOut]
    by_name: list[NameVolumeOut]
    classification_agreement: AgreementOut
    quality: list[SourceQualityOut] = Field(description="Verdicts de l'appelant sur ce run, par méthode.")
    confusion: list[ConfusionOut]


class GlobalMetricsOut(BaseModel):
    runs: int
    pages: int
    classification_agreement: AgreementOut
    quality: list[SourceQualityOut]
    by_name: list[NameQualityOut]
    confusion: list[ConfusionOut]
