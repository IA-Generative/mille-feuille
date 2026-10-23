"""Les mêmes parcours que les tests du magasin, contre un vrai serveur Qdrant (l'index de payload, l'IDF et la bascule
d'alias se comportent autrement que dans le Qdrant local des autres tests).

Ignorés sans serveur : `QDRANT_TEST_URL=http://localhost:6333 QDRANT_TEST_API_KEY=... uv run pytest`, avec le service
`qdrant` de docker-compose."""

import os
import uuid

import pytest
from qdrant_client import QdrantClient

from app.search import embeddings, indexer, store
from app.search.retrieval import DossierSearcher

URL = os.environ.get("QDRANT_TEST_URL")
pytestmark = pytest.mark.skipif(not URL, reason="QDRANT_TEST_URL n'est pas défini")

SETTINGS = {
    "strategy": "classique",
    "chunk_model": None,
    "size": 80,
    "overlap": 10,
    "window": 1,
    "embedding_model": "m",
}
VOCAB = ["loyer", "salaire", "banque"]


@pytest.fixture
def server(monkeypatch):
    client = QdrantClient(url=URL, api_key=os.environ.get("QDRANT_TEST_API_KEY") or None)
    monkeypatch.setattr(store, "get_client", lambda: client)
    monkeypatch.setattr(
        embeddings,
        "embed_dense",
        lambda texts, model: [[t.lower().replace("bail", "loyer").count(w) + 0.01 for w in VOCAB] for t in texts],
    )
    dossier_id = f"it-{uuid.uuid4().hex[:8]}"
    yield client, dossier_id
    store.drop_dossier(client, dossier_id)


def dossier(dossier_id: str) -> dict:
    pages = [
        {"id": "p1", "page_number": 1, "content": "Le loyer mensuel est de 800 euros. " * 6},
        {"id": "p2", "page_number": 2, "content": "IBAN FR76 3000 6000 0112 3456 7890 189 à la banque."},
    ]
    return {"id": dossier_id, "documents": [{"id": "doc", "name": "pièce.pdf", "source": None, "pages": pages}]}


def test_hybrid_search_blue_green_swap_and_drop_on_a_real_server(server):
    client, dossier_id = server
    name = store.collection_name(dossier_id, "fp1")
    indexer.reconcile(client, name, dossier(dossier_id), settings=SETTINGS, fingerprint="fp1")
    assert store.swap_alias(client, dossier_id, name) is None

    searcher = DossierSearcher(dossier_id, config={"index_settings": SETTINGS})
    assert searcher.search("FR76 3000 6000")[0].page_number == 2  # lexical
    assert searcher.search("montant du bail")[0].page_number == 1  # sémantique
    assert searcher.search("FR76 3000 6000", mode="sparse")[0].page_number == 2

    other = store.collection_name(dossier_id, "fp2")
    indexer.reconcile(client, other, dossier(dossier_id), settings=SETTINGS, fingerprint="fp2")
    assert store.swap_alias(client, dossier_id, other) == name
    assert store.active_collection(client, dossier_id) == other
    assert searcher.search("FR76 3000 6000")[0].page_number == 2  # la recherche suit l'alias

    store.drop_dossier(client, dossier_id)
    assert store.active_collection(client, dossier_id) is None
    assert not client.collection_exists(name) and not client.collection_exists(other)
