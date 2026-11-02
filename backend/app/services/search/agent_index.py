"""L'index des agents d'une analyse : retrouver, par recherche hybride, celui dont le rôle correspond à la question.

Une collection Qdrant par modèle d'embeddings (la dimension des vecteurs en dépend), commune à toutes les analyses :
chaque point est un agent, filtré par `analyse_id`. Le texte indexé est le nom et le début du prompt ; un point garde
l'empreinte de son texte, pour que la synchronisation ne refasse que ce qui a changé. Le client Qdrant est synchrone :
les appels passent par un thread."""

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client import models as m

from app.config import SearchSettings as PlatformSearchSettings
from app.services.search import qdrant_store as store
from app.services.search.embeddings import embed_dense, embed_query, encode_sparse, encode_sparse_query
from app.services.search.settings import SearchSettings

logger = logging.getLogger(__name__)

TEXT_CHARS = 2000
_NAMESPACE = uuid.UUID("0c7a3a5e-5f0f-4a8e-8d11-6a2f7c9b1d33")
_FIELDS = ("analyse_id", "agent_id")


@dataclass(frozen=True)
class IndexedAgent:
    id: str
    name: str
    prompt: str


def embedding_model_of(stored_settings: dict | None) -> str:
    """Le modèle d'embeddings de l'analyse (celui de la plateforme à défaut) ; vide si aucun n'est configuré."""
    chosen = SearchSettings.model_validate(stored_settings or {}).embedding_model
    return chosen or PlatformSearchSettings().SEARCH_EMBEDDING_MODEL


def configured() -> bool:
    return PlatformSearchSettings().qdrant_configured


def collection_for(model: str) -> str:
    return f"agents_{hashlib.sha256(model.encode()).hexdigest()[:10]}"


def point_id(agent_id: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, agent_id))


def agent_text(agent: IndexedAgent) -> str:
    return f"{agent.name}\n{' '.join(agent.prompt.split())}"[:TEXT_CHARS]


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _of_analyse(analyse_id: str) -> m.Filter:
    return m.Filter(must=[m.FieldCondition(key="analyse_id", match=m.MatchValue(value=analyse_id))])


def _existing(client: QdrantClient, collection: str, analyse_id: str) -> dict[str, tuple[str, str]]:
    """Les agents déjà indexés de l'analyse : identifiant de l'agent -> (identifiant du point, empreinte du texte)."""
    if not client.collection_exists(collection):
        return {}
    points, _next = client.scroll(collection, scroll_filter=_of_analyse(analyse_id), limit=1000, with_payload=True)
    return {p.payload["agent_id"]: (str(p.id), p.payload.get("text_hash", "")) for p in points}


def sync_analyse(analyse_id: str, agents: list[IndexedAgent], model: str) -> dict[str, int]:
    """Met l'index des agents de l'analyse à jour : ajoute ou refait ceux dont le texte a changé, retire ceux qui ne
    sont plus dans l'analyse. Sans effet quand tout est déjà à jour. Bloquant : à appeler dans un thread."""
    client = store.get_client()
    collection = collection_for(model)
    existing = _existing(client, collection, analyse_id)
    texts = {agent.id: agent_text(agent) for agent in agents}
    changed = [agent for agent in agents if existing.get(agent.id, ("", ""))[1] != _hash(texts[agent.id])]
    if changed:
        vectors = embed_dense([texts[agent.id] for agent in changed], model)
        store.create_collection(client, collection, len(vectors[0]), _FIELDS)
        store.upsert(
            client,
            collection,
            [
                {
                    "id": point_id(agent.id),
                    "dense": vector,
                    "sparse": encode_sparse(texts[agent.id]),
                    "payload": {
                        "analyse_id": analyse_id,
                        "agent_id": agent.id,
                        "name": agent.name,
                        "text_hash": _hash(texts[agent.id]),
                    },
                }
                for agent, vector in zip(changed, vectors, strict=True)
            ],
        )
    stale = [point for agent_id, (point, _hash_) in existing.items() if agent_id not in texts]
    store.delete_points(client, collection, stale)
    return {"indexed": len(changed), "removed": len(stale)}


async def find(analyse_id: str, question: str, model: str, limit: int) -> list[str]:
    """Les identifiants des agents de l'analyse qui répondent le mieux à la question, du plus pertinent au moins."""
    dense = await embed_query(question, model)
    points = await asyncio.to_thread(
        store.hybrid_query,
        store.get_client(),
        collection_for(model),
        dense=dense,
        sparse=encode_sparse_query(question),
        limit=limit,
        query_filter=_of_analyse(analyse_id),
    )
    return [point.payload["agent_id"] for point in points]
