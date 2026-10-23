from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_EXTERNAL_SOURCES_PER_MESSAGE = 10


class ExternalBox(BaseModel):
    """Une zone à surligner, en coordonnées normalisées 0..1 (origine en haut à gauche)."""

    page: int = Field(ge=1)
    x_min: float = Field(ge=0, le=1)
    y_min: float = Field(ge=0, le=1)
    x_max: float = Field(ge=0, le=1)
    y_max: float = Field(ge=0, le=1)


class ExternalSourceIn(BaseModel):
    """Une source consultée par l'assistant, déposée par le worker avec le message."""

    source_id: str
    # Le numéro cité dans la réponse (suite commune avec les sources du dossier).
    number: int | None = Field(default=None, ge=1)
    kind: Literal["document", "web"]
    title: str
    url: str
    preview_url: str | None = None
    page: int | None = Field(default=None, ge=1)
    boxes: list[ExternalBox] = []
    passage: str
    score: float = Field(ge=0, le=1)
    collection_id: str = ""
    collection_name: str = ""
    source_name: str = ""


class ExternalSourceOut(ExternalSourceIn):
    model_config = ConfigDict(from_attributes=True)

    position: int
