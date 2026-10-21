import uuid
from datetime import date

from pydantic import BaseModel, Field

from app.models.token_usage import TokenUsageKind


class UsageSums(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0


class StepUsage(UsageSums):
    step: str


class DayUsage(UsageSums):
    day: date


class ModelUsage(UsageSums):
    model: str


class UserUsage(UsageSums):
    # None pour les appels qu'on ne sait rattacher à personne (classification, extraction...).
    user_id: str | None
    display: str | None


class UsageOut(BaseModel):
    days: int
    totals: UsageSums
    by_step: list[StepUsage]
    by_day: list[DayUsage]
    by_model: list[ModelUsage]
    # Administrateurs seulement : toujours vide sur la consommation d'une personne.
    by_user: list[UserUsage]


class UsageIn(BaseModel):
    """Un appel au LLM déposé par un worker."""

    step: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    kind: TokenUsageKind = TokenUsageKind.CHAT
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    user_id: str | None = None
    dossier_id: uuid.UUID | None = None
