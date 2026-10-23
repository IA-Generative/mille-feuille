import pytest
from qdrant_client import QdrantClient

from app.search import store


@pytest.fixture
def client(monkeypatch):
    memory = QdrantClient(":memory:")
    monkeypatch.setattr(store, "get_client", lambda: memory)
    return memory


def _point(page_id: str, index: int, dense: list[float], terms: dict[int, float], **payload) -> dict:
    return {
        "id": store.point_id(page_id, index),
        "dense": dense,
        "sparse": {"indices": list(terms), "values": list(terms.values())},
        "payload": {"page_id": page_id, "document_id": payload.pop("document_id", "doc"), **payload},
    }


def test_point_id_is_stable_and_distinct():
    assert store.point_id("p1", 0) == store.point_id("p1", 0)
    assert store.point_id("p1", 0) != store.point_id("p1", 1)
    assert store.point_id("p1", 0) != store.point_id("p2", 0)


def test_no_index_means_no_active_collection_and_no_result(client):
    assert store.active_collection(client, "d1") is None
    assert store.hybrid_search(client, "d1", dense=[1, 0, 0], sparse={"indices": [], "values": []}) == []


def test_swap_alias_points_the_dossier_at_the_collection(client):
    store.create_collection(client, "dossier_d1_a", 3)
    assert store.swap_alias(client, "d1", "dossier_d1_a") is None
    assert store.active_collection(client, "d1") == "dossier_d1_a"


def test_swap_alias_replaces_the_previous_one_and_names_it(client):
    store.create_collection(client, "dossier_d1_a", 3)
    store.create_collection(client, "dossier_d1_b", 4)
    store.swap_alias(client, "d1", "dossier_d1_a")
    assert store.swap_alias(client, "d1", "dossier_d1_b") == "dossier_d1_a"
    assert store.active_collection(client, "d1") == "dossier_d1_b"


def test_hybrid_search_finds_a_lexical_only_and_a_dense_only_match(client):
    store.create_collection(client, "dossier_d1_a", 3)
    store.upsert(
        client,
        "dossier_d1_a",
        [
            _point("p1", 0, [1, 0, 0], {10: 1.0}, text="dense"),
            _point("p2", 0, [0, 1, 0], {20: 1.0}, text="lexical"),
            _point("p3", 0, [0, 0, 1], {30: 1.0}, text="neither"),
        ],
    )
    store.swap_alias(client, "d1", "dossier_d1_a")

    dense_hit = store.hybrid_search(client, "d1", dense=[1, 0, 0], sparse={"indices": [], "values": []}, limit=1)
    assert dense_hit[0].payload["text"] == "dense"
    lexical_hit = store.hybrid_search(client, "d1", dense=[0.2, 0.2, 0.2], sparse={"indices": [20], "values": [1.0]})
    assert lexical_hit[0].payload["text"] == "lexical"


def test_search_never_reads_another_dossier(client):
    for dossier in ("d1", "d2"):
        name = store.collection_name(dossier, "a")
        store.create_collection(client, name, 3)
        store.upsert(client, name, [_point(f"page-{dossier}", 0, [1, 0, 0], {1: 1.0}, text=f"texte {dossier}")])
        store.swap_alias(client, dossier, name)

    hits = store.hybrid_search(client, "d1", dense=[1, 0, 0], sparse={"indices": [1], "values": [1.0]})
    assert [hit.payload["text"] for hit in hits] == ["texte d1"]


def test_delete_document_and_scroll(client):
    store.create_collection(client, "dossier_d1_a", 3)
    store.upsert(
        client,
        "dossier_d1_a",
        [
            _point("p1", 0, [1, 0, 0], {1: 1.0}, document_id="doc-a", text_hash="h1", fingerprint="f"),
            _point("p2", 0, [0, 1, 0], {2: 1.0}, document_id="doc-b", text_hash="h2", fingerprint="f"),
        ],
    )
    store.delete_document(client, "dossier_d1_a", "doc-a")
    points = list(store.scroll(client, "dossier_d1_a"))
    assert [(p.page_id, p.text_hash) for p in points] == [("p2", "h2")]
    assert store.count(client, "dossier_d1_a") == 1


def test_drop_dossier_removes_alias_and_every_collection(client):
    for fingerprint in ("a", "b"):
        store.create_collection(client, store.collection_name("d1", fingerprint), 3)
    store.create_collection(client, store.collection_name("d2", "a"), 3)
    store.swap_alias(client, "d1", store.collection_name("d1", "a"))

    store.drop_dossier(client, "d1")

    assert store.active_collection(client, "d1") is None
    assert [c.name for c in client.get_collections().collections] == [store.collection_name("d2", "a")]
