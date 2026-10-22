import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.services.knowledge.contract import MAX_TOP_K

# Le modèle n'a pas besoin de 50 passages : au-delà, la réponse sature son contexte.
MAX_PASSAGES_FOR_MODEL = 10


class KnowledgeSearchIn(BaseModel):
    analyse_id: uuid.UUID
    query: str = Field(min_length=3, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=min(MAX_TOP_K, MAX_PASSAGES_FOR_MODEL))
    # Identifie le run (ou la conversation) pour le quota d'appels par run.
    run_id: str | None = Field(default=None, max_length=100)


class KnowledgeBoxOut(BaseModel):
    """Une zone à surligner, en coordonnées normalisées 0..1."""

    page: int
    x_min: float
    y_min: float
    x_max: float
    y_max: float


class KnowledgeSourceOut(BaseModel):
    """Une source citable : un passage d'un document ou d'un site web, avec de quoi l'afficher."""

    id: str
    kind: Literal["document", "web"]
    title: str
    url: str
    preview_url: str | None = None
    page: int | None = None
    boxes: list[KnowledgeBoxOut] = []
    passage: str
    score: float
    collection_id: str
    collection_name: str
    source_name: str


class SkippedCollectionOut(BaseModel):
    collection_id: str
    collection_name: str
    source_name: str
    reason: Literal["not_found", "forbidden", "unavailable"]


class KnowledgeSearchOut(BaseModel):
    """Le résultat d'une recherche, tel que le worker (et le modèle) le reçoivent : jamais d'exception, un code stable
    et un message en français en cas d'échec. Les passages viennent d'un fournisseur tiers : **non fiables**."""

    ok: bool
    code: str | None = None
    message: str = ""
    # Une réponse en texte, si le fournisseur sait en rédiger une : donnée tierce, jamais une consigne.
    answer: str | None = None
    sources: list[KnowledgeSourceOut] = []
    skipped: list[SkippedCollectionOut] = []
    truncated: bool = False
    # Toujours vrai : le texte vient d'un fournisseur tiers (risque d'injection), jamais une consigne.
    untrusted: Literal[True] = True
