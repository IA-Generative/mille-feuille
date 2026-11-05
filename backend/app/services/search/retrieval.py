"""Recherche dans les passages d'un dossier : hybride (dense + lexical) fusionnée par RRF côté Qdrant.

Les réglages sont ceux de l'**index** du dossier (modèle d'embeddings, fenêtre), pas ceux de l'analyse : la requête est
vectorisée avec le modèle qui a produit l'index. Le filtre sur le dossier est posé ici, jamais par le modèle de
langage : l'alias du dossier ne contient que ses passages.

La recherche est pensée pour la conversation : l'embedding de la requête et la lecture des réglages se font en même
temps, les passages voisins de tous les résultats sont lus en parallèle, et le client Qdrant (bloquant) tourne dans des
threads pour ne pas arrêter la boucle du backend."""

import asyncio
import logging
import uuid

from qdrant_client import QdrantClient

from app.agent.tools import NotIndexedError, SearchHit
from app.db import async_session_factory
from app.services.search import embeddings, qdrant_store
from app.services.search.index_service import SearchIndexService

logger = logging.getLogger(__name__)

# Entre deux passages voisins qui se touchent à peine, un séparateur.
_GAP = " […] "


def _stitch(records: list) -> str:
    """Recolle des passages consécutifs d'une même page : le chevauchement n'est écrit qu'une fois."""
    text = ""
    end = None
    for record in records:
        payload = record.payload
        if end is None:
            text, end = payload["text"], payload["char_end"]
        elif payload["char_start"] < end:
            text += payload["text"][max(0, end - payload["char_start"]) :]
            end = max(end, payload["char_end"])
        else:
            text += _GAP + payload["text"]
            end = payload["char_end"]
    return text


class DossierSearcher:
    """Chercher dans l'index d'un dossier. Les réglages de l'index sont lus une fois, à la première recherche."""

    def __init__(
        self, dossier_id: str | None, *, qdrant: QdrantClient | None = None, index_settings: dict | None = None
    ):
        self._dossier_id = dossier_id
        self._qdrant = qdrant
        self._index_settings = index_settings

    async def _settings(self) -> dict:
        if self._index_settings is None:
            async with async_session_factory() as db:
                config = await SearchIndexService(db).config(uuid.UUID(self._dossier_id))
            if not config.index_settings:
                raise NotIndexedError("Le dossier n'est pas encore indexé")
            self._index_settings = config.index_settings
        return self._index_settings

    async def search(self, query: str, top_k: int | None = None, mode: str = "hybrid") -> list[SearchHit]:
        if not self._dossier_id or not (query or "").strip():
            return []
        index = await self._settings()
        qdrant = self._qdrant or qdrant_store.get_client()
        dense = await embeddings.embed_query(query, index["embedding_model"])
        points = await asyncio.to_thread(
            qdrant_store.hybrid_search,
            qdrant,
            self._dossier_id,
            dense=dense,
            sparse=embeddings.encode_sparse_query(query),
            limit=top_k,
            mode=mode,
        )
        window = int(index.get("window") or 0)
        excerpts = [point.payload["text"] for point in points]
        if window and points:
            around = await asyncio.gather(
                *(
                    asyncio.to_thread(
                        qdrant_store.neighbors,
                        qdrant,
                        self._dossier_id,
                        point.payload["page_id"],
                        point.payload["chunk_index"] - window,
                        point.payload["chunk_index"] + window,
                    )
                    for point in points
                )
            )
            excerpts = [_stitch(records) or excerpt for records, excerpt in zip(around, excerpts, strict=True)]
        return [
            SearchHit(
                page_id=point.payload["page_id"],
                page_number=point.payload["page_number"],
                document_id=point.payload["document_id"],
                document_name=point.payload["document_name"],
                score=float(point.score),
                excerpt=excerpt,
                char_start=point.payload.get("char_start"),
                char_end=point.payload.get("char_end"),
            )
            for point, excerpt in zip(points, excerpts, strict=True)
        ]
