import pytest
from qdrant_client import QdrantClient

from app.search import embeddings, indexer, store

SETTINGS = {
    "strategy": "classique",
    "chunk_model": None,
    "size": 100,
    "overlap": 10,
    "window": 1,
    "embedding_model": "bge",
}


@pytest.fixture
def client(monkeypatch):
    memory = QdrantClient(":memory:")
    monkeypatch.setattr(store, "get_client", lambda: memory)
    monkeypatch.setattr(
        embeddings,
        "embed_dense",
        lambda texts, model: [[float(len(text) % 7), 1.0, float(sum(map(ord, text)) % 5)] for text in texts],
    )
    return memory


def page(page_id: str, number: int, content: str) -> dict:
    return {"id": page_id, "page_number": number, "content": content}


def dossier_of(*documents: dict) -> dict:
    return {"id": "d1", "documents": list(documents)}


def document(doc_id: str, *pages: dict, name: str = "pièce.pdf", source: str | None = None) -> dict:
    return {"id": doc_id, "name": name, "source": {"name": source} if source else None, "pages": list(pages)}


LONG = " ".join(f"mot{i}" for i in range(60))  # ~ 290 caractères : plusieurs passages de 100


def count(client, collection="c") -> int:
    return store.count(client, collection)


def test_a_page_becomes_chunks_with_position_and_metadata(client):
    doc = document("doc", page("p1", 1, LONG), source="Guichet")
    written = indexer.index_page(
        client, "c", dossier_id="d1", document=doc, page=doc["pages"][0], settings=SETTINGS, fingerprint="f1"
    )

    points = client.scroll("c", limit=50, with_payload=True)[0]
    assert written == len(points) > 2
    first = min(points, key=lambda p: p.payload["chunk_index"]).payload
    assert first["dossier_id"] == "d1" and first["document_id"] == "doc"
    assert first["document_name"] == "pièce.pdf — source : Guichet"
    assert first["page_number"] == 1 and first["fingerprint"] == "f1"
    assert LONG[first["char_start"] : first["char_end"]] == first["text"]
    assert first["text_hash"] == indexer.page_hash(LONG)


def test_reindexing_a_page_replaces_its_chunks_instead_of_piling_up(client):
    doc = document("doc", page("p1", 1, LONG))
    indexer.index_page(
        client, "c", dossier_id="d1", document=doc, page=doc["pages"][0], settings=SETTINGS, fingerprint="f"
    )
    before = count(client)
    indexer.index_page(
        client,
        "c",
        dossier_id="d1",
        document=doc,
        page={**doc["pages"][0], "content": "court"},
        settings=SETTINGS,
        fingerprint="f",
    )
    assert before > 2 and count(client) == 1


def test_a_blank_page_writes_nothing(client):
    doc = document("doc", page("p1", 1, "   "))
    assert (
        indexer.index_page(
            client, "c", dossier_id="d1", document=doc, page=doc["pages"][0], settings=SETTINGS, fingerprint="f"
        )
        == 0
    )
    assert not client.collection_exists("c")


def test_reconcile_indexes_a_new_dossier_then_does_nothing_more(client):
    dossier = dossier_of(
        document("a", page("p1", 1, LONG), page("p2", 2, "Une autre page.")), document("b", page("p3", 1, LONG))
    )
    first = indexer.reconcile(client, "c", dossier, settings=SETTINGS, fingerprint="f")
    assert first.pages_written == 3 and first.chunks_written == count(client) and first.changed

    second = indexer.reconcile(client, "c", dossier, settings=SETTINGS, fingerprint="f")
    assert second.pages_written == 0 and not second.changed


def test_reconcile_catches_added_changed_and_removed_pages(client):
    dossier = dossier_of(document("a", page("p1", 1, LONG), page("p2", 2, "Deuxième page.")))
    indexer.reconcile(client, "c", dossier, settings=SETTINGS, fingerprint="f")

    changed = dossier_of(
        document("a", page("p1", 1, LONG + " modifié"), page("p4", 3, "Page ajoutée.")),  # p2 retirée
    )
    result = indexer.reconcile(client, "c", changed, settings=SETTINGS, fingerprint="f")

    assert result.pages_written == 2 and result.points_removed == 1
    pages = {point.page_id for point in store.scroll(client, "c")}
    assert pages == {"p1", "p4"}


def test_reconcile_rewrites_everything_when_the_fingerprint_changes(client):
    dossier = dossier_of(document("a", page("p1", 1, LONG), page("p2", 2, "Deuxième page.")))
    indexer.reconcile(client, "c", dossier, settings=SETTINGS, fingerprint="f")

    result = indexer.reconcile(client, "c", dossier, settings=SETTINGS, fingerprint="g")

    assert result.pages_written == 2
    assert {point.fingerprint for point in store.scroll(client, "c")} == {"g"}


def test_reconcile_resumes_where_a_crash_stopped(client):
    dossier = dossier_of(document("a", page("p1", 1, "Un."), page("p2", 2, "Deux."), page("p3", 3, "Trois.")))

    def crash_after_first(_chunks: int) -> None:
        raise RuntimeError("worker tué")

    with pytest.raises(RuntimeError):
        indexer.reconcile(client, "c", dossier, settings=SETTINGS, fingerprint="f", on_page=crash_after_first)
    assert {p.page_id for p in store.scroll(client, "c")} == {"p1"}

    result = indexer.reconcile(client, "c", dossier, settings=SETTINGS, fingerprint="f")
    assert result.pages_written == 2


def test_reconcile_skips_pages_without_text(client):
    dossier = dossier_of(document("a", page("p1", 1, ""), page("p2", 2, "Du texte.")))
    assert indexer.reconcile(client, "c", dossier, settings=SETTINGS, fingerprint="f").pages_written == 1


def test_reconcile_progress_callback_gets_each_page_chunk_count(client):
    seen: list[int] = []
    dossier = dossier_of(document("a", page("p1", 1, "Court."), page("p2", 2, LONG)))
    indexer.reconcile(client, "c", dossier, settings=SETTINGS, fingerprint="f", on_page=seen.append)
    assert seen[0] == 1 and seen[1] > 2
