"""Indexation d'un dossier et reconstruction blue/green : Qdrant (en mémoire) et les embeddings sont simulés, les
comptes rendus au service d'index sont gardés."""

from types import SimpleNamespace

import pytest
from qdrant_client import QdrantClient

from app.services.search import embeddings, indexing
from app.services.search import qdrant_store as store

pytestmark = pytest.mark.anyio

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
    """Le service d'index vu par l'indexation : un dossier, ses réglages, et le journal de ce qui lui a été rendu."""

    def __init__(self) -> None:
        self.dossier = {"id": "d1", "documents": [doc("a", ("p1", TEXT))]}
        self.config: dict = {"effective": OLD, "fingerprint": OLD_FP, "problem": None}
        self.reports: list[dict] = []
        self.rebuild: dict = {}
        self.rebuild_reports: list[dict] = []
        self.on_get_dossier = None

    async def fresh_dossier(self, dossier_id):
        if self.on_get_dossier:
            self.on_get_dossier(self)
        return self.dossier

    async def get_config(self, dossier_id):
        return SimpleNamespace(
            **{
                key: self.config.get(key) for key in ("index_settings", "index_fingerprint", "effective", "fingerprint")
            },
            problem=self.config.get("problem"),
        )

    async def report_index(self, dossier_id, report):
        self.reports.append(report.model_dump(exclude_unset=True))

    async def get_rebuild(self, rebuild_id):
        return SimpleNamespace(**self.rebuild) if self.rebuild else None

    async def report_rebuild(self, rebuild_id, report):
        body = report.model_dump(exclude_unset=True)
        self.rebuild_reports.append(body)
        if "status" in body:
            self.rebuild = {**self.rebuild, "status": body["status"]}


@pytest.fixture
def backend(monkeypatch):
    fake = FakeBackend()
    memory = QdrantClient(":memory:")
    monkeypatch.setattr(indexing, "_fresh_dossier", fake.fresh_dossier)
    monkeypatch.setattr(indexing, "_config", fake.get_config)
    monkeypatch.setattr(indexing, "_report_index", fake.report_index)
    monkeypatch.setattr(indexing, "_rebuild", fake.get_rebuild)
    monkeypatch.setattr(indexing, "_report_rebuild", fake.report_rebuild)
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
        "target_settings": NEW,
        "previous_fingerprint": previous,
    }
    backend.config = {
        **backend.config,
        "index_fingerprint": previous,
        "index_settings": OLD if previous else None,
    }


def active(backend: FakeBackend) -> str | None:
    return store.active_collection(backend.qdrant, "d1")


def pages_in(backend: FakeBackend, collection: str) -> set[str]:
    return {p.page_id for p in store.scroll(backend.qdrant, collection)}


# --- Indexation d'un document ---


async def test_the_first_document_creates_the_index_and_the_alias(backend):
    await indexing.index_document("d1", "a")

    assert active(backend) == store.collection_name("d1", OLD_FP)
    assert pages_in(backend, active(backend)) == {"p1"}
    assert [r["status"] for r in backend.reports] == ["indexing", "ready"]
    assert backend.reports[0]["fingerprint"] == OLD_FP and backend.reports[0]["settings"] == OLD
    assert backend.reports[1]["chunk_count"] == store.count(backend.qdrant, active(backend)) > 2


async def test_a_later_document_is_indexed_with_the_settings_of_the_existing_index(backend):
    await indexing.index_document("d1", "a")
    # L'analyse a changé depuis, mais le dossier garde son index : le document suit l'index.
    backend.config = {
        **backend.config,
        "effective": NEW,
        "fingerprint": NEW_FP,
        "index_fingerprint": OLD_FP,
        "index_settings": OLD,
    }
    backend.dossier = {"id": "d1", "documents": [*backend.dossier["documents"], doc("b", ("p2", "Une autre page."))]}

    await indexing.index_document("d1", "b")

    assert active(backend) == store.collection_name("d1", OLD_FP)
    assert pages_in(backend, active(backend)) == {"p1", "p2"}
    assert {p.fingerprint for p in store.scroll(backend.qdrant, active(backend))} == {OLD_FP}


async def test_indexing_a_document_does_not_touch_the_other_documents(backend):
    backend.dossier = {"id": "d1", "documents": [doc("a", ("p1", TEXT)), doc("b", ("p2", "Deux."))]}
    await indexing.index_document("d1", "a")
    await indexing.index_document("d1", "b")
    await indexing.index_document("d1", "a")  # relancée : ne retire pas p2

    assert pages_in(backend, active(backend)) == {"p1", "p2"}


async def test_a_dossier_whose_settings_cannot_be_resolved_is_not_indexed(backend):
    backend.config = {"effective": None, "fingerprint": None, "problem": "Aucun modèle d'embeddings"}

    await indexing.index_document("d1", "a")

    assert backend.reports == [] and active(backend) is None


async def test_a_failure_is_reported_as_an_error_status(backend, monkeypatch):
    def boom(texts, model):
        raise RuntimeError("hub indisponible")

    monkeypatch.setattr(embeddings, "embed_dense", boom)

    await indexing.index_document("d1", "a")

    assert backend.reports[-1] == {"status": "error", "error": "hub indisponible"}
    assert active(backend) is None


# --- Reconstruction blue/green ---


async def test_a_first_indexation_by_rebuild_ends_without_anything_to_validate(backend):
    start_rebuild(backend, previous=None)

    await indexing.rebuild_index("r1")

    assert active(backend) == store.collection_name("d1", NEW_FP)
    assert backend.rebuild_reports[-1] == {"status": "finalized"}
    swap_report = next(r for r in backend.reports if r.get("replace_settings"))
    assert swap_report["fingerprint"] == NEW_FP and swap_report["settings"] == NEW


async def test_a_rebuild_keeps_the_old_index_serving_until_the_swap(backend):
    await indexing.index_document("d1", "a")
    old = active(backend)
    seen: list[str | None] = []
    backend.on_get_dossier = lambda _b: seen.append(active(backend))
    start_rebuild(backend, previous=OLD_FP)

    await indexing.rebuild_index("r1")

    assert set(seen[:-1]) == {old}  # pendant la construction, l'alias reste sur l'ancien
    assert active(backend) == store.collection_name("d1", NEW_FP)
    assert backend.qdrant.collection_exists(old)  # gardé jusqu'à la validation
    assert backend.rebuild_reports[-1] == {"status": "swapped"}
    assert pages_in(backend, active(backend)) == {"p1"}
    assert {p.fingerprint for p in store.scroll(backend.qdrant, active(backend))} == {NEW_FP}


async def test_progress_is_reported_in_pages(backend):
    backend.dossier = {"id": "d1", "documents": [doc("a", ("p1", TEXT), ("p2", "Deux."), ("p3", "Trois."))]}
    start_rebuild(backend, previous=None)

    await indexing.rebuild_index("r1")

    progress = [r for r in backend.rebuild_reports if "total_pages" in r]
    assert progress[0] == {"total_pages": 3, "done_pages": 0}
    assert progress[-1] == {"total_pages": 3, "done_pages": 3}


async def test_a_document_added_during_the_build_is_caught(backend):
    await indexing.index_document("d1", "a")
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

    await indexing.rebuild_index("r1")

    assert pages_in(backend, active(backend)) == {"p1", "p9"}


async def test_a_document_arriving_during_the_swap_is_caught_by_the_final_pass(backend):
    start_rebuild(backend, previous=None)
    reads = {"n": 0}

    def late_document(b: FakeBackend) -> None:
        reads["n"] += 1
        # La dernière lecture (après la bascule) voit un document de plus.
        if b.rebuild_reports and any(r.get("status") == "finalized" for r in b.rebuild_reports):
            b.dossier = {"id": "d1", "documents": [*b.dossier["documents"], doc("b", ("p7", "Tardif."))]}

    backend.on_get_dossier = late_document

    await indexing.rebuild_index("r1")

    assert "p7" in pages_in(backend, active(backend))


async def test_a_failed_build_leaves_the_old_index_active_and_drops_the_partial_one(backend, monkeypatch):
    await indexing.index_document("d1", "a")
    old = active(backend)
    start_rebuild(backend, previous=OLD_FP)

    def boom(texts, model):
        raise RuntimeError("quota dépassé")

    monkeypatch.setattr(embeddings, "embed_dense", boom)

    await indexing.rebuild_index("r1")

    assert active(backend) == old
    assert not backend.qdrant.collection_exists(store.collection_name("d1", NEW_FP))
    assert backend.rebuild_reports[-1] == {"status": "failed", "error": "quota dépassé"}


async def test_a_rebuild_that_is_not_building_anymore_does_nothing(backend):
    start_rebuild(backend, previous=None, status="rolled_back")
    await indexing.rebuild_index("r1")
    assert active(backend) is None and backend.rebuild_reports == []


async def test_a_rebuild_cancelled_during_the_build_does_not_swap(backend):
    await indexing.index_document("d1", "a")
    old = active(backend)
    start_rebuild(backend, previous=OLD_FP)
    backend.on_get_dossier = lambda b: b.rebuild.update(status="rolled_back")

    await indexing.rebuild_index("r1")

    assert active(backend) == old


async def test_a_dossier_without_text_cannot_be_rebuilt(backend):
    backend.dossier = {"id": "d1", "documents": [doc("a", ("p1", "  "))]}
    start_rebuild(backend, previous=None)
    await indexing.rebuild_index("r1")
    assert backend.rebuild_reports[-1]["status"] == "failed"


# --- Validation, retour arrière, suppression ---


async def swapped(backend: FakeBackend) -> str:
    await indexing.index_document("d1", "a")
    old = active(backend)
    start_rebuild(backend, previous=OLD_FP)
    await indexing.rebuild_index("r1")
    return old


async def test_validation_drops_the_old_index(backend):
    old = await swapped(backend)
    backend.rebuild = {**backend.rebuild, "status": "finalized"}

    await indexing.finalize_rebuild("r1")

    assert not backend.qdrant.collection_exists(old)
    assert backend.qdrant.collection_exists(active(backend))


async def test_validation_never_drops_the_active_index(backend):
    await swapped(backend)
    backend.rebuild = {**backend.rebuild, "previous_fingerprint": NEW_FP}  # cas absurde : l'« ancien » est l'actif
    await indexing.finalize_rebuild("r1")
    assert backend.qdrant.collection_exists(active(backend))


async def test_rollback_after_the_swap_puts_the_alias_back_and_drops_the_new_index(backend):
    old = await swapped(backend)
    new = active(backend)
    backend.rebuild = {**backend.rebuild, "status": "rolled_back"}

    await indexing.rollback_rebuild("r1")

    assert active(backend) == old and not backend.qdrant.collection_exists(new)
    assert backend.reports[-1]["status"] == "ready"


async def test_rollback_before_the_swap_only_drops_the_building_index(backend):
    await indexing.index_document("d1", "a")
    old = active(backend)
    building = store.collection_name("d1", NEW_FP)
    store.create_collection(backend.qdrant, building, 3)
    start_rebuild(backend, previous=OLD_FP, status="rolled_back")

    await indexing.rollback_rebuild("r1")

    assert active(backend) == old and not backend.qdrant.collection_exists(building)


async def test_dropping_a_dossier_removes_its_alias_and_collections(backend):
    await swapped(backend)
    await indexing.drop_dossier_index("d1")
    assert active(backend) is None and backend.qdrant.get_collections().collections == []
