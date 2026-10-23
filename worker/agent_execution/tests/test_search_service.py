from contextlib import contextmanager

import pytest
from qdrant_client import QdrantClient

from app import api_client
from app.search import embeddings, service, store

OLD = {"strategy": "classique", "chunk_model": None, "size": 100, "overlap": 10, "window": 1, "embedding_model": "m1"}
NEW = {**OLD, "embedding_model": "m2"}
OLD_FP, NEW_FP = "oldfp", "newfp"
TEXT = " ".join(f"mot{i}" for i in range(40))  # plusieurs passages de 100 caractères


def doc(doc_id: str, *pages: tuple[str, str]) -> dict:
    return {
        "id": doc_id,
        "name": f"{doc_id}.pdf",
        "source": None,
        "pages": [{"id": pid, "page_number": n, "content": text} for n, (pid, text) in enumerate(pages, 1)],
    }


class FakeBackend:
    """Le backend vu par le worker : un dossier, ses réglages, et le journal de ce que le worker lui a dit."""

    def __init__(self) -> None:
        self.dossier = {"id": "d1", "documents": [doc("a", ("p1", TEXT))]}
        self.config: dict = {"effective": OLD, "fingerprint": OLD_FP, "problem": None, "rebuild": None}
        self.reports: list[dict] = []
        self.rebuild: dict = {}
        self.rebuild_reports: list[dict] = []
        self.on_get_dossier = None

    # api_client
    def get_dossier(self, client, dossier_id):
        if self.on_get_dossier:
            self.on_get_dossier(self)
        return self.dossier

    def get_search_config(self, client, dossier_id):
        return self.config

    def report_search_index(self, client, dossier_id, **body):
        self.reports.append(body)

    def get_index_rebuild(self, client, rebuild_id):
        return self.rebuild

    def report_index_rebuild(self, client, rebuild_id, **body):
        self.rebuild_reports.append(body)
        if "status" in body:
            self.rebuild = {**self.rebuild, "status": body["status"]}
        return self.rebuild


@pytest.fixture
def backend(monkeypatch):
    fake = FakeBackend()
    memory = QdrantClient(":memory:")

    @contextmanager
    def fake_client():
        yield object()

    monkeypatch.setattr(api_client, "get_client", fake_client)
    for name in (
        "get_dossier",
        "get_search_config",
        "report_search_index",
        "get_index_rebuild",
        "report_index_rebuild",
    ):
        monkeypatch.setattr(api_client, name, getattr(fake, name))
    monkeypatch.setattr(store, "get_client", lambda: memory)
    monkeypatch.setattr(
        embeddings, "embed_dense", lambda texts, model: [[float(len(t) % 5), 1.0, float(len(model))] for t in texts]
    )
    fake.qdrant = memory
    return fake


def start_rebuild(backend: FakeBackend, *, previous: str | None, status: str = "building") -> None:
    backend.rebuild = {
        "id": "r1",
        "dossier_id": "d1",
        "status": status,
        "target_fingerprint": NEW_FP,
        "previous_fingerprint": previous,
    }
    backend.config = {
        **backend.config,
        "rebuild": backend.rebuild,
        "rebuild_target_settings": NEW,
        "index_fingerprint": previous,
        "index_settings": OLD if previous else None,
    }


def active(backend: FakeBackend) -> str | None:
    return store.active_collection(backend.qdrant, "d1")


def pages_in(backend: FakeBackend, collection: str) -> set[str]:
    return {p.page_id for p in store.scroll(backend.qdrant, collection)}


# --- Indexation d'un document ---


def test_the_first_document_creates_the_index_and_the_alias(backend):
    service.index_document("d1", "a")

    assert active(backend) == store.collection_name("d1", OLD_FP)
    assert pages_in(backend, active(backend)) == {"p1"}
    assert [r["status"] for r in backend.reports] == ["indexing", "ready"]
    assert backend.reports[0]["fingerprint"] == OLD_FP and backend.reports[0]["settings"] == OLD
    assert backend.reports[1]["chunk_count"] == store.count(backend.qdrant, active(backend)) > 2


def test_a_later_document_is_indexed_with_the_settings_of_the_existing_index(backend):
    service.index_document("d1", "a")
    # L'analyse a changé depuis, mais le dossier garde son index : le document suit l'index.
    backend.config = {
        **backend.config,
        "effective": NEW,
        "fingerprint": NEW_FP,
        "index_fingerprint": OLD_FP,
        "index_settings": OLD,
    }
    backend.dossier = {"id": "d1", "documents": [*backend.dossier["documents"], doc("b", ("p2", "Une autre page."))]}

    service.index_document("d1", "b")

    assert active(backend) == store.collection_name("d1", OLD_FP)
    assert pages_in(backend, active(backend)) == {"p1", "p2"}
    assert {p.fingerprint for p in store.scroll(backend.qdrant, active(backend))} == {OLD_FP}


def test_indexing_a_document_does_not_touch_the_other_documents(backend):
    backend.dossier = {"id": "d1", "documents": [doc("a", ("p1", TEXT)), doc("b", ("p2", "Deux."))]}
    service.index_document("d1", "a")
    service.index_document("d1", "b")
    service.index_document("d1", "a")  # relancée : ne retire pas p2

    assert pages_in(backend, active(backend)) == {"p1", "p2"}


def test_a_dossier_whose_settings_cannot_be_resolved_is_not_indexed(backend):
    backend.config = {"effective": None, "fingerprint": None, "problem": "Aucun modèle d'embeddings"}

    service.index_document("d1", "a")

    assert backend.reports == [] and active(backend) is None


def test_a_failure_is_reported_as_an_error_status(backend, monkeypatch):
    def boom(texts, model):
        raise RuntimeError("hub indisponible")

    monkeypatch.setattr(embeddings, "embed_dense", boom)

    with pytest.raises(RuntimeError):
        service.index_document("d1", "a")

    assert backend.reports[-1] == {"status": "error", "error": "hub indisponible"}
    assert active(backend) is None


def test_removing_a_document_clears_it_from_the_active_and_the_building_index(backend):
    backend.dossier = {"id": "d1", "documents": [doc("a", ("p1", TEXT)), doc("b", ("p2", "Deux."))]}
    service.index_document("d1", "a")
    service.index_document("d1", "b")
    building = store.collection_name("d1", NEW_FP)
    store.create_collection(backend.qdrant, building, 3)
    start_rebuild(backend, previous=OLD_FP)
    from app.search import indexer

    indexer.reconcile(backend.qdrant, building, backend.dossier, settings=NEW, fingerprint=NEW_FP)

    service.remove_document("d1", "b")

    assert pages_in(backend, active(backend)) == {"p1"} and pages_in(backend, building) == {"p1"}


# --- Reconstruction blue/green ---


def test_a_first_indexation_by_rebuild_ends_without_anything_to_validate(backend):
    start_rebuild(backend, previous=None)

    service.rebuild_index("r1")

    assert active(backend) == store.collection_name("d1", NEW_FP)
    assert backend.rebuild_reports[-1] == {"status": "finalized"}
    swap_report = next(r for r in backend.reports if r.get("replace_settings"))
    assert swap_report["fingerprint"] == NEW_FP and swap_report["settings"] == NEW


def test_a_rebuild_keeps_the_old_index_serving_until_the_swap(backend):
    service.index_document("d1", "a")
    old = active(backend)
    seen: list[str | None] = []
    backend.on_get_dossier = lambda _b: seen.append(active(backend))
    start_rebuild(backend, previous=OLD_FP)

    service.rebuild_index("r1")

    assert set(seen[:-1]) == {old}  # pendant la construction, l'alias reste sur l'ancien
    assert active(backend) == store.collection_name("d1", NEW_FP)
    assert backend.qdrant.collection_exists(old)  # gardé jusqu'à la validation
    assert backend.rebuild_reports[-1] == {"status": "swapped"}
    assert pages_in(backend, active(backend)) == {"p1"}
    assert {p.fingerprint for p in store.scroll(backend.qdrant, active(backend))} == {NEW_FP}


def test_progress_is_reported_in_pages(backend):
    backend.dossier = {"id": "d1", "documents": [doc("a", ("p1", TEXT), ("p2", "Deux."), ("p3", "Trois."))]}
    start_rebuild(backend, previous=None)

    service.rebuild_index("r1")

    progress = [r for r in backend.rebuild_reports if "total_pages" in r]
    assert progress[0] == {"total_pages": 3, "done_pages": 0}
    assert progress[-1] == {"total_pages": 3, "done_pages": 3}


def test_a_document_added_during_the_build_is_caught(backend):
    service.index_document("d1", "a")
    start_rebuild(backend, previous=OLD_FP)
    calls = {"n": 0}

    def add_a_document_on_the_second_read(b: FakeBackend) -> None:
        calls["n"] += 1
        if calls["n"] == 3:
            b.dossier = {
                "id": "d1",
                "documents": [*b.dossier["documents"], doc("b", ("p9", "Arrivé en cours de route."))],
            }

    backend.on_get_dossier = add_a_document_on_the_second_read

    service.rebuild_index("r1")

    assert pages_in(backend, active(backend)) == {"p1", "p9"}


def test_a_document_arriving_during_the_swap_is_caught_by_the_final_pass(backend):
    start_rebuild(backend, previous=None)
    reads = {"n": 0}

    def late_document(b: FakeBackend) -> None:
        reads["n"] += 1
        # La dernière lecture (après la bascule) voit un document de plus.
        if b.rebuild_reports and any(r.get("status") == "finalized" for r in b.rebuild_reports):
            b.dossier = {"id": "d1", "documents": [*b.dossier["documents"], doc("b", ("p7", "Tardif."))]}

    backend.on_get_dossier = late_document

    service.rebuild_index("r1")

    assert "p7" in pages_in(backend, active(backend))


def test_a_failed_build_leaves_the_old_index_active_and_drops_the_partial_one(backend, monkeypatch):
    service.index_document("d1", "a")
    old = active(backend)
    start_rebuild(backend, previous=OLD_FP)

    def boom(texts, model):
        raise RuntimeError("quota dépassé")

    monkeypatch.setattr(embeddings, "embed_dense", boom)

    service.rebuild_index("r1")

    assert active(backend) == old
    assert not backend.qdrant.collection_exists(store.collection_name("d1", NEW_FP))
    assert backend.rebuild_reports[-1] == {"status": "failed", "error": "quota dépassé"}


def test_a_rebuild_that_is_not_building_anymore_does_nothing(backend):
    start_rebuild(backend, previous=None, status="rolled_back")
    service.rebuild_index("r1")
    assert active(backend) is None and backend.rebuild_reports == []


def test_a_rebuild_cancelled_during_the_build_does_not_swap(backend):
    service.index_document("d1", "a")
    old = active(backend)
    start_rebuild(backend, previous=OLD_FP)
    backend.on_get_dossier = lambda b: b.rebuild.update(status="rolled_back")

    service.rebuild_index("r1")

    assert active(backend) == old


def test_a_dossier_without_text_cannot_be_rebuilt(backend):
    backend.dossier = {"id": "d1", "documents": [doc("a", ("p1", "  "))]}
    start_rebuild(backend, previous=None)
    service.rebuild_index("r1")
    assert backend.rebuild_reports[-1]["status"] == "failed"


# --- Validation, retour arrière, suppression ---


def swapped(backend: FakeBackend) -> str:
    service.index_document("d1", "a")
    old = active(backend)
    start_rebuild(backend, previous=OLD_FP)
    service.rebuild_index("r1")
    return old


def test_validation_drops_the_old_index(backend):
    old = swapped(backend)
    backend.rebuild = {**backend.rebuild, "status": "finalized"}

    service.finalize_rebuild("r1")

    assert not backend.qdrant.collection_exists(old)
    assert backend.qdrant.collection_exists(active(backend))


def test_validation_never_drops_the_active_index(backend):
    swapped(backend)
    backend.rebuild = {**backend.rebuild, "previous_fingerprint": NEW_FP}  # cas absurde : l'« ancien » est l'actif
    service.finalize_rebuild("r1")
    assert backend.qdrant.collection_exists(active(backend))


def test_rollback_after_the_swap_puts_the_alias_back_and_drops_the_new_index(backend):
    old = swapped(backend)
    new = active(backend)
    backend.rebuild = {**backend.rebuild, "status": "rolled_back"}

    service.rollback_rebuild("r1")

    assert active(backend) == old and not backend.qdrant.collection_exists(new)
    assert backend.reports[-1]["status"] == "ready"


def test_rollback_before_the_swap_only_drops_the_building_index(backend):
    service.index_document("d1", "a")
    old = active(backend)
    building = store.collection_name("d1", NEW_FP)
    store.create_collection(backend.qdrant, building, 3)
    start_rebuild(backend, previous=OLD_FP, status="rolled_back")

    service.rollback_rebuild("r1")

    assert active(backend) == old and not backend.qdrant.collection_exists(building)


def test_dropping_a_dossier_removes_its_alias_and_collections(backend):
    swapped(backend)
    service.drop_dossier_index("d1")
    assert active(backend) is None and backend.qdrant.get_collections().collections == []
