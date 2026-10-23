import pytest
from qdrant_client import QdrantClient

from app.search import embeddings, indexer, store
from app.search.retrieval import DossierSearcher, NotIndexedError

SETTINGS = {
    "strategy": "classique",
    "chunk_model": None,
    "size": 60,
    "overlap": 10,
    "window": 0,
    "embedding_model": "bge",
}
VOCAB = ["loyer", "charges", "salaire", "adresse", "contrat", "banque"]


def fake_dense(texts, model):
    """Un embedding « sémantique » jouet : chaque mot du vocabulaire est un axe, et « bail » veut dire « loyer »."""
    vectors = []
    for text in texts:
        lowered = text.lower().replace("bail", "loyer")
        vectors.append([float(lowered.count(word)) + 0.01 for word in VOCAB])
    return vectors


@pytest.fixture
def client(monkeypatch):
    memory = QdrantClient(":memory:")
    monkeypatch.setattr(store, "get_client", lambda: memory)
    monkeypatch.setattr(embeddings, "embed_dense", fake_dense)
    return memory


def build(client, dossier_id: str, pages: dict[str, str], settings=SETTINGS) -> None:
    documents = [
        {
            "id": f"doc-{pid}",
            "name": f"{pid}.pdf",
            "source": None,
            "pages": [{"id": pid, "page_number": n, "content": c}],
        }
        for n, (pid, c) in enumerate(pages.items(), 1)
    ]
    name = store.collection_name(dossier_id, "fp")
    indexer.reconcile(client, name, {"id": dossier_id, "documents": documents}, settings=settings, fingerprint="fp")
    store.swap_alias(client, dossier_id, name)


def searcher(client, dossier_id="d1", **settings) -> DossierSearcher:
    return DossierSearcher(dossier_id, qdrant=client, config={"index_settings": {**SETTINGS, **settings}})


def test_a_lexical_match_is_found_even_when_the_meaning_is_far(client):
    build(client, "d1", {"p1": "IBAN FR76 3000 6000 0112 3456 7890 189", "p2": "Le loyer est de 800 euros."})
    hits = searcher(client).search("FR76 3000 6000")
    assert hits[0].page_id == "p1"


def test_a_semantic_match_is_found_without_sharing_a_word(client):
    build(client, "d1", {"p1": "Le salaire net est de 2100 euros.", "p2": "Le loyer mensuel est de 800 euros."})
    hits = searcher(client).search("montant du bail")  # « bail » ≈ « loyer » pour le modèle d'embeddings
    assert hits[0].page_id == "p2"


def test_a_hit_carries_page_document_and_score(client):
    build(client, "d1", {"p1": "Le loyer est de 800 euros."})
    hit = searcher(client).search("loyer")[0]
    assert (hit.page_id, hit.page_number, hit.document_id, hit.document_name) == ("p1", 1, "doc-p1", "p1.pdf")
    assert hit.score > 0 and "loyer" in hit.excerpt


def test_search_never_returns_another_dossiers_passages(client):
    build(client, "d1", {"p1": "Le loyer du dossier un."})
    build(client, "d2", {"p2": "Le loyer du dossier deux."})
    assert {h.page_id for h in searcher(client, "d1").search("loyer")} == {"p1"}
    assert {h.page_id for h in searcher(client, "d2").search("loyer")} == {"p2"}


def test_top_k_limits_the_number_of_passages(client):
    build(client, "d1", {f"p{i}": f"Le loyer numéro {i} est payé." for i in range(10)})
    assert len(searcher(client).search("loyer", top_k=3)) == 3


LONG = ". ".join(f"Phrase {i} sur le dossier" for i in range(12)) + "."


def test_a_window_adds_the_neighbouring_passages_without_repeating_the_overlap(client):
    build(client, "d1", {"p1": LONG})
    alone = searcher(client, window=0).search("Phrase 6")[0].excerpt
    around = searcher(client, window=1).search("Phrase 6")[0].excerpt

    assert len(around) > len(alone)
    assert alone in around or alone[10:] in around
    assert around.count("Phrase 6") == 1  # le chevauchement n'est écrit qu'une fois


def test_the_window_stays_inside_the_page(client):
    build(client, "d1", {"p1": LONG, "p2": "Une autre page sur le loyer."})
    assert "autre page" not in searcher(client, window=3).search("Phrase 6")[0].excerpt


def test_an_unindexed_dossier_raises_so_the_tool_can_say_so(client):
    with pytest.raises(NotIndexedError):
        DossierSearcher("d1", qdrant=client, config={"index_settings": None}).search("loyer")


def test_a_dossier_without_alias_finds_nothing(client):
    assert searcher(client, "inconnu").search("loyer") == []


def test_blank_query_or_missing_dossier_finds_nothing(client):
    build(client, "d1", {"p1": "Le loyer."})
    assert searcher(client).search("   ") == []
    assert DossierSearcher(None, qdrant=client, config={"index_settings": SETTINGS}).search("loyer") == []


def test_the_query_is_embedded_with_the_model_of_the_index(client, monkeypatch):
    build(client, "d1", {"p1": "Le loyer."})
    seen: list[str] = []
    monkeypatch.setattr(
        embeddings, "embed_dense", lambda texts, model: (seen.append(model), fake_dense(texts, model))[1]
    )
    searcher(client, embedding_model="le-modele-de-l-index").search("loyer")
    assert seen == ["le-modele-de-l-index"]


def test_settings_are_read_from_the_backend_once(client, monkeypatch):
    from contextlib import contextmanager

    from app import api_client

    build(client, "d1", {"p1": "Le loyer."})
    reads: list[str] = []

    @contextmanager
    def fake_client():
        yield object()

    monkeypatch.setattr(api_client, "get_client", fake_client)
    monkeypatch.setattr(
        api_client,
        "get_search_config",
        lambda c, dossier_id: (reads.append(dossier_id), {"index_settings": SETTINGS})[1],
    )
    lazy = DossierSearcher("d1", qdrant=client)
    lazy.search("loyer")
    lazy.search("loyer")
    assert reads == ["d1"]
