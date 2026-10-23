"""Écriture des passages d'un dossier dans une collection Qdrant.

L'unité de travail est la **page** : une page est découpée, vectorisée puis écrite en une fois, après avoir effacé ses
anciens passages. Une page indexée porte l'empreinte des réglages et le hash de son texte ; `reconcile` compare ce que
la collection contient à ce que le dossier devrait y avoir (pages manquantes, texte changé, autre empreinte, pages
disparues) et ne refait que la différence. C'est ce qui rend l'indexation reprenable et la reconstruction blue/green
correcte même si le dossier change pendant qu'elle tourne."""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass

from qdrant_client import QdrantClient

from app.search import embeddings, store
from app.search.chunking import ChunkingSettings, split_page

logger = logging.getLogger(__name__)


def page_hash(content: str | None) -> str:
    return hashlib.sha256((content or "").encode()).hexdigest()[:16]


def document_name(document: dict) -> str:
    """Nom du document, suivi de sa source s'il en a une (« passeport.pdf — source : Guichet »)."""
    name = document.get("name", "")
    source = (document.get("source") or {}).get("name")
    return f"{name} — source : {source}" if source else name


def chunking_settings(settings: dict) -> ChunkingSettings:
    return ChunkingSettings.from_dict(
        {
            "strategy": settings.get("strategy"),
            "model": settings.get("chunk_model"),
            "size": settings.get("size"),
            "overlap": settings.get("overlap"),
            "window": settings.get("window"),
        }
    )


def index_page(
    client: QdrantClient,
    collection: str,
    *,
    dossier_id: str,
    document: dict,
    page: dict,
    settings: dict,
    fingerprint: str,
) -> int:
    """Découpe, vectorise et écrit une page ; renvoie le nombre de passages. Les anciens passages de la page sont
    effacés avant l'écriture : une page rechoupée en moins de passages ne laisse rien derrière elle."""
    content = page.get("content") or ""
    chunks = split_page(content, chunking_settings(settings))
    if client.collection_exists(collection):
        store.delete_page(client, collection, page["id"])
    if not chunks:
        return 0
    dense = embeddings.embed_dense([chunk.text for chunk in chunks], settings["embedding_model"])
    store.create_collection(client, collection, len(dense[0]))
    digest = page_hash(content)
    name = document_name(document)
    points = [
        {
            "id": store.point_id(page["id"], index),
            "dense": dense[index],
            "sparse": embeddings.encode_sparse(chunk.text),
            "payload": {
                "dossier_id": dossier_id,
                "document_id": document["id"],
                "document_name": name,
                "page_id": page["id"],
                "page_number": page["page_number"],
                "chunk_index": index,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "text": chunk.text,
                "text_hash": digest,
                "fingerprint": fingerprint,
            },
        }
        for index, chunk in enumerate(chunks)
    ]
    store.upsert(client, collection, points)
    return len(points)


@dataclass
class Reconciliation:
    pages_written: int = 0
    chunks_written: int = 0
    points_removed: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.pages_written or self.points_removed)


def reconcile(
    client: QdrantClient,
    collection: str,
    dossier: dict,
    *,
    settings: dict,
    fingerprint: str,
    on_page: Callable[[int], None] | None = None,
) -> Reconciliation:
    """Met la collection d'accord avec le dossier : n'écrit que les pages manquantes ou modifiées, et retire les
    passages des pages qui n'existent plus. `on_page` reçoit le nombre de passages après chaque page écrite."""
    result = Reconciliation()
    indexed: dict[str, tuple[str, str]] = {}
    if client.collection_exists(collection):
        for point in store.scroll(client, collection):
            indexed[point.page_id] = (point.text_hash, point.fingerprint)

    wanted: dict[str, tuple[dict, dict]] = {}
    for document in dossier.get("documents", []):
        for page in document.get("pages", []):
            if (page.get("content") or "").strip():
                wanted[page["id"]] = (document, page)

    gone = [page_id for page_id in indexed if page_id not in wanted]
    for page_id in gone:
        store.delete_page(client, collection, page_id)
        result.points_removed += 1

    for page_id, (document, page) in wanted.items():
        if indexed.get(page_id) == (page_hash(page.get("content")), fingerprint):
            continue
        written = index_page(
            client,
            collection,
            dossier_id=dossier["id"],
            document=document,
            page=page,
            settings=settings,
            fingerprint=fingerprint,
        )
        result.pages_written += 1
        result.chunks_written += written
        if on_page:
            on_page(written)
    return result
