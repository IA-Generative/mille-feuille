"""Les définitions d'entités des analyses dans Qdrant, pour **proposer** des équivalences (#649).

Seules les définitions sont vectorisées (nom, définition, type) : jamais le contenu des dossiers ni les valeurs
extraites. L'index est mis à jour à la demande, d'après l'empreinte de chaque définition."""

import asyncio
import hashlib
import uuid
from dataclasses import dataclass

from qdrant_client import models as m

from app.config import ResemblanceSettings, SearchSettings
from app.services.search import qdrant_store as store
from app.services.search.embeddings import embed_dense, encode_sparse

_NAMESPACE = uuid.UUID("5b1e2f3a-7c4d-4e8f-9a0b-1c2d3e4f5a6b")
_FIELDS = ("entity_id", "type")
SUGGESTIONS = 8


@dataclass(frozen=True)
class IndexedEntity:
    id: str
    name: str
    definition: str
    type: str


def model() -> str:
    return SearchSettings().SEARCH_EMBEDDING_MODEL


def available() -> bool:
    return SearchSettings().qdrant_configured and bool(model())


def _collection() -> str:
    return f"entity_definitions_{hashlib.sha256(model().encode()).hexdigest()[:10]}"


def _text(entity: IndexedEntity) -> str:
    return f"{entity.name}\n{' '.join(entity.definition.split())}"[:2000]


def _hash(entity: IndexedEntity) -> str:
    return hashlib.sha256(f"{entity.type}\n{_text(entity)}".encode()).hexdigest()[:16]


def _suggest(entities: list[IndexedEntity], queries: list[tuple[str, str | None]], excluded: set[str]) -> list[str]:
    """Synchronise l'index puis cherche. `queries` : (texte, type exigé ou None). Bloquant."""
    client = store.get_client()
    collection = _collection()
    existing: dict[str, tuple[str, str]] = {}
    if client.collection_exists(collection):
        offset = None
        while True:
            points, offset = client.scroll(collection, limit=500, offset=offset, with_payload=True)
            existing.update({p.payload["entity_id"]: (str(p.id), p.payload.get("hash", "")) for p in points})
            if offset is None:
                break
    changed = [e for e in entities if existing.get(e.id, ("", ""))[1] != _hash(e)]
    if changed:
        vectors = embed_dense([_text(e) for e in changed], model())
        store.create_collection(client, collection, len(vectors[0]), _FIELDS)
        store.upsert(
            client,
            collection,
            [
                {
                    "id": str(uuid.uuid5(_NAMESPACE, e.id)),
                    "dense": vector,
                    "sparse": encode_sparse(_text(e)),
                    "payload": {"entity_id": e.id, "type": e.type, "hash": _hash(e)},
                }
                for e, vector in zip(changed, vectors, strict=True)
            ],
        )
    known = {e.id for e in entities}
    store.delete_points(client, collection, [point for key, (point, _) in existing.items() if key not in known])
    if not queries or not client.collection_exists(collection):
        return []

    best: dict[str, float] = {}
    vectors = embed_dense([text for text, _ in queries], model())
    for (_, kind), vector in zip(queries, vectors, strict=True):
        must = [m.FieldCondition(key="type", match=m.MatchValue(value=kind))] if kind else []
        must_not = [m.FieldCondition(key="entity_id", match=m.MatchAny(any=sorted(excluded)))] if excluded else []
        result = client.query_points(
            collection,
            query=vector,
            using=store.DENSE,
            query_filter=m.Filter(must=must, must_not=must_not),
            score_threshold=ResemblanceSettings().RESEMBLANCE_SUGGESTION_MIN_SCORE,
            limit=SUGGESTIONS,
            with_payload=True,
        )
        for point in result.points:
            key = point.payload["entity_id"]
            best[key] = max(best.get(key, 0.0), point.score)
    return sorted(best, key=lambda key: -best[key])[:SUGGESTIONS]


async def suggest(entities: list[IndexedEntity], *, entity_ids: list[str], text: str) -> list[str]:
    by_id = {e.id: e for e in entities}
    queries = [(_text(by_id[i]), by_id[i].type) for i in entity_ids if i in by_id]
    if text.strip():
        queries.append((text.strip(), None))
    return await asyncio.to_thread(_suggest, entities, queries, set(entity_ids))
