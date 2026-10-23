"""Recherche dans les passages d'un dossier : hybride (dense + lexical) fusionnée par RRF côté Qdrant.

Les réglages sont ceux de l'**index** du dossier (modèle d'embeddings, fenêtre), pas ceux de l'analyse : la requête est
vectorisée avec le modèle qui a produit l'index. Le filtre sur le dossier est posé ici, jamais par le modèle de
langage : l'alias du dossier ne contient que ses passages."""

import logging
from dataclasses import dataclass

from qdrant_client import QdrantClient

from app import api_client
from app.search import embeddings, store

logger = logging.getLogger(__name__)

# Entre deux passages voisins qui se touchent à peine, un séparateur.
_GAP = " […] "


class NotIndexedError(Exception):
    """Le dossier n'a pas (encore) d'index de recherche."""


@dataclass
class SearchHit:
    page_id: str
    page_number: int
    document_id: str
    document_name: str
    score: float
    # Le passage trouvé, entouré de ses voisins (fenêtre) et recollé sans répéter le chevauchement.
    excerpt: str


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
    """Chercher dans l'index d'un dossier. Les réglages de l'index sont lus au backend à la première recherche."""

    def __init__(self, dossier_id: str | None, *, qdrant: QdrantClient | None = None, config: dict | None = None):
        self._dossier_id = dossier_id
        self._qdrant = qdrant
        self._config = config

    def _index_settings(self) -> dict:
        if self._config is None:
            with api_client.get_client() as client:
                self._config = api_client.get_search_config(client, self._dossier_id)
        index_settings = self._config.get("index_settings")
        if not index_settings:
            raise NotIndexedError("Le dossier n'est pas encore indexé")
        return index_settings

    def search(self, query: str, top_k: int | None = None) -> list[SearchHit]:
        if not self._dossier_id or not (query or "").strip():
            return []
        index = self._index_settings()
        qdrant = self._qdrant or store.get_client()
        dense = embeddings.embed_dense([query], index["embedding_model"])[0]
        points = store.hybrid_search(
            qdrant, self._dossier_id, dense=dense, sparse=embeddings.encode_sparse_query(query), limit=top_k
        )
        window = int(index.get("window") or 0)
        hits: list[SearchHit] = []
        for point in points:
            payload = point.payload
            excerpt = payload["text"]
            if window:
                index_of = payload["chunk_index"]
                around = store.neighbors(
                    qdrant, self._dossier_id, payload["page_id"], index_of - window, index_of + window
                )
                excerpt = _stitch(around) or excerpt
            hits.append(
                SearchHit(
                    page_id=payload["page_id"],
                    page_number=payload["page_number"],
                    document_id=payload["document_id"],
                    document_name=payload["document_name"],
                    score=float(point.score),
                    excerpt=excerpt,
                )
            )
        return hits
