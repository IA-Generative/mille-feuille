"""Les réponses d'un fournisseur de collections, validées contre le contrat docs/backend/base-de-connaissances-api.yaml.

Ce que renvoie un fournisseur est une donnée tierce : on ne garde que les champs du contrat, avec leurs types. Un champ
manquant ou d'un autre type rend la réponse invalide (`invalid_response`), jamais à moitié lue."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_COLLECTION_IDS = 20
MAX_TOP_K = 50
MIN_QUERY_LENGTH = 3
DEFAULT_MAX_CHARS = 4000


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


class Passage(_Contract):
    passage_id: str
    collection_id: str
    document_id: str
    document_name: str
    page: int | None = Field(default=None, ge=1)
    text: str
    score: float = Field(ge=0, le=1)
    source_url: str | None = None
    metadata: dict[str, Any] = {}
    # Le texte a été coupé à `max_chars` par la plateforme (le fournisseur ne l'a pas fait).
    truncated: bool = False


class SkippedCollection(_Contract):
    collection_id: str
    reason: Literal["not_found", "forbidden", "unavailable"]


class Usage(_Contract):
    input_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class SearchResult(_Contract):
    items: list[Passage]
    skipped: list[SkippedCollection]
    usage: Usage | None = None


class SearchRequest(BaseModel):
    """Une recherche, bornée comme le contrat l'exige : refusée ici plutôt que par le fournisseur."""

    query: str = Field(min_length=MIN_QUERY_LENGTH, max_length=2000)
    collection_ids: list[str] = Field(min_length=1, max_length=MAX_COLLECTION_IDS)
    top_k: int = Field(default=5, ge=1, le=MAX_TOP_K)
    min_score: float | None = Field(default=None, ge=0, le=1)
    filters: dict[str, str | int | float | bool] | None = None
    max_chars: int = Field(default=DEFAULT_MAX_CHARS, ge=200, le=20000)
