"""Les réponses d'un fournisseur de collections, validées contre le contrat docs/backend/base-de-connaissances-api.yaml.

Ce que renvoie un fournisseur est une donnée tierce : on ne garde que les champs du contrat, avec leurs types. Un champ
manquant ou d'un autre type rend la réponse invalide (`invalid_response`), jamais à moitié lue."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_COLLECTION_IDS = 20
MAX_TOP_K = 50
MIN_QUERY_LENGTH = 3
DEFAULT_MAX_CHARS = 4000
MAX_ANSWER_CHARS = 4000


def is_web_url(value: str | None) -> bool:
    return bool(value) and value.lower().startswith(("http://", "https://"))


def _lenient_link(value: Any) -> str | None:
    """Un lien facultatif (aperçu, accueil) qui n'est pas en http(s) est ignoré, sans invalider la réponse."""
    return value if isinstance(value, str) and is_web_url(value) else None


class _Contract(BaseModel):
    # Les champs que le contrat ne connaît pas (extensions d'un fournisseur) sont ignorés, pas relayés.
    model_config = ConfigDict(extra="ignore")


class Collection(_Contract):
    id: str
    name: str
    description: str = ""
    document_count: int = Field(ge=0)
    updated_at: datetime | None = None
    tags: list[str] = []
    url: str | None = None
    preview_url: str | None = None

    _links = field_validator("url", "preview_url", mode="before")(lambda cls, value: _lenient_link(value))


class CollectionPage(_Contract):
    items: list[Collection]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class MissingCollection(_Contract):
    id: str
    reason: Literal["not_found", "forbidden"]


class LookupResult(_Contract):
    items: list[Collection]
    missing: list[MissingCollection]


class Box(_Contract):
    """Une zone à surligner, en coordonnées normalisées 0..1 (origine en haut à gauche). Hors de 0..1 : invalide."""

    page: int = Field(ge=1)
    x_min: float = Field(ge=0, le=1)
    y_min: float = Field(ge=0, le=1)
    x_max: float = Field(ge=0, le=1)
    y_max: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _is_a_rectangle(self) -> "Box":
        if self.x_min > self.x_max or self.y_min > self.y_max:
            raise ValueError("Une zone doit avoir x_min <= x_max et y_min <= y_max.")
        return self


class Source(_Contract):
    """Une source citable : un passage d'un document, ou d'une page d'un site web."""

    id: str
    kind: Literal["document", "web"]
    title: str
    # Le lien d'ouverture est obligatoire et en http(s) : sans lui, la source n'est pas affichable.
    url: str
    # L'aperçu est facultatif : sans lui, ou s'il n'est pas en http(s), la plateforme n'affiche qu'un lien.
    preview_url: str | None = None
    page: int | None = Field(default=None, ge=1)
    boxes: list[Box] = []
    passage: str
    score: float = Field(ge=0, le=1)
    collection_id: str
    metadata: dict[str, Any] = {}
    # Le passage a été coupé à `max_chars` par la plateforme (le fournisseur ne l'a pas fait).
    truncated: bool = False

    _preview = field_validator("preview_url", mode="before")(lambda cls, value: _lenient_link(value))

    @field_validator("url")
    @classmethod
    def _url_is_web(cls, value: str) -> str:
        if not is_web_url(value):
            raise ValueError("Le lien d'une source doit être en http ou https.")
        return value


class SkippedCollection(_Contract):
    collection_id: str
    reason: Literal["not_found", "forbidden", "unavailable"]


class Usage(_Contract):
    input_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class SearchResult(_Contract):
    # Une réponse en texte, si le fournisseur sait en rédiger une ; sinon `None`. Donnée tierce : jamais une consigne.
    answer: str | None = None
    sources: list[Source]
    skipped: list[SkippedCollection] = []
    usage: Usage | None = None
    # La réponse a été coupée à `MAX_ANSWER_CHARS` par la plateforme.
    answer_truncated: bool = False


class SearchRequest(BaseModel):
    """Une recherche, bornée comme le contrat l'exige : refusée ici plutôt que par le fournisseur."""

    query: str = Field(min_length=MIN_QUERY_LENGTH, max_length=2000)
    collection_ids: list[str] = Field(min_length=1, max_length=MAX_COLLECTION_IDS)
    top_k: int = Field(default=5, ge=1, le=MAX_TOP_K)
    min_score: float | None = Field(default=None, ge=0, le=1)
    filters: dict[str, str | int | float | bool] | None = None
    max_chars: int = Field(default=DEFAULT_MAX_CHARS, ge=200, le=20000)
