"""Index Qdrant d'un dossier.

Chaque dossier a un **alias** `dossier_<id>` qui désigne la collection active ; une reconstruction (nouveaux réglages)
crée une autre collection à côté et fait basculer l'alias en une seule opération atomique (blue/green). Les
recherches passent toujours par l'alias, jamais par le nom réel de la collection.

Deux vecteurs nommés par point : `dense` (embedding, cosinus) et `sparse` (lexical BM25 ; le serveur applique l'IDF).
"""

import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client import models as m

from app.config import settings

logger = logging.getLogger(__name__)

DENSE = "dense"
SPARSE = "sparse"

# Espace de noms des identifiants de points : un passage garde son identifiant d'une indexation à l'autre.
_POINT_NAMESPACE = uuid.UUID("5b6a1c1e-7d0f-4a39-9d2e-3c8f6b1a2e40")

# Champs de payload sur lesquels on filtre ou supprime.
_INDEXED_FIELDS = ("document_id", "page_id")


@lru_cache(maxsize=1)
def get_client() -> QdrantClient:
    if not settings.search_configured:
        raise RuntimeError("QDRANT_URL doit être configuré pour utiliser la recherche dans les dossiers.")
    if settings.QDRANT_URL == ":memory:":
        return QdrantClient(":memory:")
    return QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)


def alias_name(dossier_id: str) -> str:
    return f"dossier_{dossier_id}"


def collection_name(dossier_id: str, fingerprint: str) -> str:
    """Nom réel d'une collection : celui de l'alias, suivi de l'empreinte des réglages qui l'ont produite."""
    return f"{alias_name(dossier_id)}_{fingerprint}"


def point_id(page_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(_POINT_NAMESPACE, f"{page_id}:{chunk_index}"))


@dataclass
class IndexedPoint:
    """Ce que la reconstruction a besoin de savoir d'un point déjà écrit."""

    id: str
    page_id: str
    document_id: str
    text_hash: str
    fingerprint: str


def active_collection(client: QdrantClient, dossier_id: str) -> str | None:
    """La collection que l'alias du dossier désigne, ou None si le dossier n'a pas encore d'index."""
    alias = alias_name(dossier_id)
    for description in client.get_aliases().aliases:
        if description.alias_name == alias:
            return description.collection_name
    return None


def create_collection(client: QdrantClient, name: str, dimension: int) -> None:
    """Crée la collection (sans effet si elle existe déjà) : un vecteur dense de la dimension du modèle et un vecteur
    creux dont l'IDF est calculé par le serveur."""
    if client.collection_exists(name):
        return
    client.create_collection(
        collection_name=name,
        vectors_config={DENSE: m.VectorParams(size=dimension, distance=m.Distance.COSINE)},
        sparse_vectors_config={SPARSE: m.SparseVectorParams(modifier=m.Modifier.IDF)},
    )
    for field in _INDEXED_FIELDS:
        client.create_payload_index(name, field_name=field, field_schema=m.PayloadSchemaType.KEYWORD)


def point_structs(points: list[dict]) -> list[m.PointStruct]:
    return [
        m.PointStruct(
            id=point["id"],
            vector={
                DENSE: point["dense"],
                SPARSE: m.SparseVector(indices=point["sparse"]["indices"], values=point["sparse"]["values"]),
            },
            payload=point["payload"],
        )
        for point in points
    ]


def upsert(client: QdrantClient, collection: str, points: list[dict]) -> None:
    """Écrit un lot de points ; `wait=True` pour qu'une lecture juste après les voie."""
    if points:
        client.upsert(collection, points=point_structs(points), wait=True)


def delete_points(client: QdrantClient, collection: str, ids: list[str]) -> None:
    if ids:
        client.delete(collection, points_selector=m.PointIdsList(points=ids), wait=True)


def delete_page(client: QdrantClient, collection: str, page_id: str) -> None:
    client.delete(
        collection,
        points_selector=m.FilterSelector(
            filter=m.Filter(must=[m.FieldCondition(key="page_id", match=m.MatchValue(value=page_id))])
        ),
        wait=True,
    )


def delete_document(client: QdrantClient, collection: str, document_id: str) -> None:
    client.delete(
        collection,
        points_selector=m.FilterSelector(
            filter=m.Filter(must=[m.FieldCondition(key="document_id", match=m.MatchValue(value=document_id))])
        ),
        wait=True,
    )


def scroll(client: QdrantClient, collection: str, batch: int = 256) -> Iterator[IndexedPoint]:
    """Parcourt tous les points d'une collection (payload seul), page après page."""
    offset = None
    while True:
        records, offset = client.scroll(collection, limit=batch, offset=offset, with_payload=True, with_vectors=False)
        for record in records:
            payload = record.payload or {}
            yield IndexedPoint(
                id=str(record.id),
                page_id=payload.get("page_id", ""),
                document_id=payload.get("document_id", ""),
                text_hash=payload.get("text_hash", ""),
                fingerprint=payload.get("fingerprint", ""),
            )
        if offset is None:
            return


def count(client: QdrantClient, collection: str) -> int:
    return client.count(collection, exact=True).count


def swap_alias(client: QdrantClient, dossier_id: str, collection: str) -> str | None:
    """Fait pointer l'alias du dossier sur `collection` en une seule opération atomique : une recherche voit l'ancienne
    collection ou la nouvelle, jamais rien entre les deux. Renvoie la collection qui était active (None au premier
    index)."""
    alias = alias_name(dossier_id)
    previous = active_collection(client, dossier_id)
    operations: list[m.AliasOperations] = []
    if previous is not None:
        operations.append(m.DeleteAliasOperation(delete_alias=m.DeleteAlias(alias_name=alias)))
    operations.append(m.CreateAliasOperation(create_alias=m.CreateAlias(collection_name=collection, alias_name=alias)))
    client.update_collection_aliases(change_aliases_operations=operations)
    return previous


def drop_collection(client: QdrantClient, name: str) -> None:
    if client.collection_exists(name):
        client.delete_collection(name)


def drop_dossier(client: QdrantClient, dossier_id: str) -> None:
    """Supprime l'index du dossier : l'alias puis toutes ses collections (active et en construction)."""
    alias = alias_name(dossier_id)
    active = active_collection(client, dossier_id)
    if active is not None:
        client.update_collection_aliases(
            change_aliases_operations=[m.DeleteAliasOperation(delete_alias=m.DeleteAlias(alias_name=alias))]
        )
    for collection in client.get_collections().collections:
        if collection.name.startswith(f"{alias}_"):
            client.delete_collection(collection.name)


def neighbors(client: QdrantClient, dossier_id: str, page_id: str, first: int, last: int) -> list[m.Record]:
    """Les passages `first` à `last` d'une page, dans l'ordre (fenêtre glissante autour d'un passage trouvé)."""
    records, _ = client.scroll(
        alias_name(dossier_id),
        scroll_filter=m.Filter(
            must=[
                m.FieldCondition(key="page_id", match=m.MatchValue(value=page_id)),
                m.FieldCondition(key="chunk_index", range=m.Range(gte=first, lte=last)),
            ]
        ),
        limit=last - first + 1,
        with_payload=True,
    )
    return sorted(records, key=lambda record: record.payload["chunk_index"])


def hybrid_search(
    client: QdrantClient,
    dossier_id: str,
    *,
    dense: list[float],
    sparse: dict,
    limit: int | None = None,
    mode: str = "hybrid",
) -> list[m.ScoredPoint]:
    """Recherche hybride sur l'alias du dossier : deux branches (dense et creuse) fusionnées par RRF. Ne cherche que
    dans ce dossier, quoi que contienne la requête. `mode` (`dense` ou `sparse`) n'interroge qu'une branche : c'est
    ce qui permet de mesurer l'apport de l'hybride (voir app.search.evaluation)."""
    if active_collection(client, dossier_id) is None:
        return []
    branch = settings.SEARCH_BRANCH_LIMIT
    prefetch = []
    if mode in ("hybrid", "dense"):
        prefetch.append(m.Prefetch(query=dense, using=DENSE, limit=branch))
    if mode in ("hybrid", "sparse") and sparse["indices"]:
        prefetch.append(
            m.Prefetch(
                query=m.SparseVector(indices=sparse["indices"], values=sparse["values"]), using=SPARSE, limit=branch
            )
        )
    if not prefetch:
        return []
    result = client.query_points(
        alias_name(dossier_id),
        prefetch=prefetch,
        query=m.RrfQuery(rrf=m.Rrf(k=settings.SEARCH_RRF_K)),
        limit=limit or settings.SEARCH_TOP_K,
        with_payload=True,
    )
    return result.points
