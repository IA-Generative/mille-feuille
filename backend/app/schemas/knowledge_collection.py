import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.analyse import Version

MAX_COLLECTIONS_PER_ANALYSE = 50


class KnowledgeCollectionRef(BaseModel):
    source_id: uuid.UUID
    collection_id: str = Field(min_length=1, max_length=200)


class KnowledgeCollectionsUpdate(BaseModel):
    """La liste **complète** des collections autorisées pour l'analyse : elle remplace l'ancienne."""

    collections: list[KnowledgeCollectionRef] = Field(max_length=MAX_COLLECTIONS_PER_ANALYSE)


class StoredKnowledgeCollection(BaseModel):
    """Ce qui est conservé (et versionné) : les identifiants, et le nom au moment du choix."""

    source_id: uuid.UUID
    collection_id: str
    name: str


# `available` : la personne la voit. `not_found` : elle n'existe plus chez le fournisseur. `forbidden` : elle existe
# mais la personne n'y a plus droit. `source_unavailable` : la source n'est plus visible, ou ne répond pas.
CollectionStatus = Literal["available", "not_found", "forbidden", "source_unavailable"]


class KnowledgeCollectionOut(StoredKnowledgeCollection):
    source_name: str
    status: CollectionStatus


class KnowledgeCollectionsOut(BaseModel):
    collections: list[KnowledgeCollectionOut]
    versions: list[Version[list[StoredKnowledgeCollection]]] = []
