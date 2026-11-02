import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.db import async_session_factory
from app.models.search_index import DossierSearchIndex
from app.schemas.search_index import IndexRebuildOut, RebuildReport, SearchIndexReport
from app.services.search import settings as search_settings
from app.services.search.index_service import SearchIndexService
from tests.document_helpers import run


@pytest.fixture(autouse=True)
def _platform_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARCH_EMBEDDING_MODEL", "bge-m3")
    monkeypatch.setenv("SEARCH_CHUNK_MODEL", "llama-decoupe")


@pytest.fixture
def dispatched(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    for name in ("rebuild_index", "finalize_rebuild", "rollback_rebuild"):
        monkeypatch.setattr(
            f"app.agent.dispatch.dispatch_{name}", lambda rebuild_id, name=name: calls.append((name, rebuild_id))
        )
    return calls


def make_dossier(client: TestClient, **settings) -> tuple[str, str]:
    analyse = client.post("/api/analyses", json={"name": f"Index {uuid.uuid4().hex[:6]}", "description": "T"}).json()[
        "id"
    ]
    if settings:
        assert client.put(f"/api/analyses/{analyse}/search-settings", json=settings).status_code == 200
    dossier = client.post("/api/dossiers", json={"name": "Dossier", "analyse_id": analyse}).json()["id"]
    return analyse, dossier


def effective(client: TestClient, analyse: str) -> dict:
    return client.get(f"/api/analyses/{analyse}/search-settings").json()["effective"]


def _service_call(client: TestClient, work):  # noqa: ANN001, ANN202
    """Ce que fait l'indexation du backend : appeler `SearchIndexService` (sur la boucle de l'application)."""

    async def run_work():  # noqa: ANN202
        async with async_session_factory() as db:
            return await work(SearchIndexService(db))

    return client.portal.call(run_work)


def report(client: TestClient, dossier: str, **body):  # noqa: ANN201
    """Le compte rendu de l'indexation sur l'index du dossier : 204, ou 422 si le compte rendu est incomplet."""

    async def run_report(service: SearchIndexService) -> int:
        try:
            await service.report_index(uuid.UUID(dossier), SearchIndexReport(**body))
        except (ValueError, ValidationError):
            return 422
        return 204

    return SimpleNamespace(status_code=_service_call(client, run_report))


def report_rebuild(client: TestClient, rebuild_id: str, **body) -> dict:  # noqa: ANN003
    """Le compte rendu de la reconstruction : la reconstruction après mise à jour."""

    async def run_report(service: SearchIndexService) -> dict:
        rebuild = await service.report_rebuild(uuid.UUID(rebuild_id), RebuildReport(**body))
        return IndexRebuildOut.model_validate(rebuild).model_dump(mode="json")

    return _service_call(client, run_report)


def search_config(client: TestClient, dossier: str) -> dict:
    """Les réglages à appliquer, l'index actif et la reconstruction en cours, tels que l'indexation les lit."""

    async def read(service: SearchIndexService) -> dict:
        return (await service.config(uuid.UUID(dossier))).model_dump(mode="json")

    return _service_call(client, read)


def first_index(client: TestClient, analyse: str, dossier: str, **extra):
    eff = effective(client, analyse)
    body = {"status": "ready", "chunk_count": 12, "fingerprint": search_settings.fingerprint(eff), "settings": eff}
    return report(client, dossier, **{**body, **extra})


# --- État ---


def test_a_new_dossier_has_no_index_and_says_what_it_would_get(client: TestClient) -> None:
    analyse, dossier = make_dossier(client)
    body = client.get(f"/api/dossiers/{dossier}/search-index").json()
    assert body["freshness"] == "none" and body["status"] is None and body["rebuild"] is None
    assert body["expected_fingerprint"] == client.get(f"/api/analyses/{analyse}/search-settings").json()["fingerprint"]


def test_an_indexed_dossier_is_current_until_the_analyse_settings_differ(client: TestClient) -> None:
    analyse, dossier = make_dossier(client, strategy="classique", embedding_model="e5")
    assert first_index(client, analyse, dossier).status_code == 204

    body = client.get(f"/api/dossiers/{dossier}/search-index").json()
    assert (body["freshness"], body["status"], body["chunk_count"]) == ("current", "ready", 12)
    assert body["indexed_at"] is not None

    # Réglages changés ailleurs : l'index n'est plus celui que donneraient les réglages (version future déverrouillée).
    async def change(session):
        from app.models.analyse import Analyse

        row = await session.get(Analyse, uuid.UUID(analyse))
        row.search_settings = {**row.search_settings, "embedding_model": "autre-modele"}
        await session.commit()

    run(client, change)
    assert client.get(f"/api/dossiers/{dossier}/search-index").json()["freshness"] == "obsolete"


def test_the_state_of_an_unknown_dossier_is_a_404(client: TestClient) -> None:
    assert client.get(f"/api/dossiers/{uuid.uuid4()}/search-index").status_code == 404


# --- Configuration lue par le worker ---


def test_the_indexation_reads_the_settings_to_apply_and_the_active_index(client: TestClient) -> None:
    analyse, dossier = make_dossier(client, strategy="classique", embedding_model="e5")
    config = search_config(client, dossier)
    assert config["effective"]["embedding_model"] == "e5" and config["index_fingerprint"] is None
    assert config["problem"] is None and config["rebuild"] is None

    first_index(client, analyse, dossier)
    config = search_config(client, dossier)
    assert config["index_settings"]["embedding_model"] == "e5" and config["index_status"] == "ready"


def test_the_first_report_must_carry_the_fingerprint_and_the_settings(client: TestClient) -> None:
    _, dossier = make_dossier(client)
    assert report(client, dossier, status="indexing").status_code == 422


def test_later_reports_update_progress_but_keep_the_settings_the_index_was_built_with(client: TestClient) -> None:
    analyse, dossier = make_dossier(client, strategy="classique", embedding_model="e5")
    first_index(client, analyse, dossier, status="indexing", chunk_count=3)
    report(client, dossier, status="ready", chunk_count=40, fingerprint="autre", settings={"x": 1})

    body = client.get(f"/api/dossiers/{dossier}/search-index").json()
    assert (body["status"], body["chunk_count"]) == ("ready", 40)
    assert body["fingerprint"] == search_settings.fingerprint(effective(client, analyse))


def test_an_error_is_reported_with_its_message(client: TestClient) -> None:
    analyse, dossier = make_dossier(client)
    first_index(client, analyse, dossier, status="error", error="hub indisponible")
    body = client.get(f"/api/dossiers/{dossier}/search-index").json()
    assert (body["status"], body["error"]) == ("error", "hub indisponible")


# --- Reconstruction blue/green ---


def force_obsolete(client: TestClient, analyse: str, **changes) -> None:
    async def change(session):
        from app.models.analyse import Analyse

        row = await session.get(Analyse, uuid.UUID(analyse))
        row.search_settings = {**row.search_settings, **changes}
        await session.commit()

    run(client, change)


def start(client: TestClient, dossier: str):
    return client.post(f"/api/dossiers/{dossier}/search-index/rebuild")


def test_a_first_indexation_is_a_rebuild_without_a_previous_index(client: TestClient, dispatched) -> None:
    analyse, dossier = make_dossier(client, strategy="classique", embedding_model="e5")

    response = start(client, dossier)

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "building" and body["previous_fingerprint"] is None
    assert body["target_fingerprint"] == search_settings.fingerprint(effective(client, analyse))
    assert dispatched == [("rebuild_index", body["id"])]
    assert client.get(f"/api/dossiers/{dossier}/search-index").json()["rebuild"]["id"] == body["id"]


def test_an_up_to_date_index_has_nothing_to_rebuild(client: TestClient, dispatched) -> None:
    analyse, dossier = make_dossier(client, strategy="classique", embedding_model="e5")
    first_index(client, analyse, dossier)

    response = start(client, dossier)

    assert response.status_code == 409 and response.json()["detail"]["code"] == "index_a_jour"
    assert dispatched == []


def test_an_index_in_error_can_be_rebuilt_with_the_same_settings(client: TestClient, dispatched) -> None:
    analyse, dossier = make_dossier(client, strategy="classique", embedding_model="e5")
    first_index(client, analyse, dossier, status="error", error="boom")
    assert start(client, dossier).status_code == 202


def test_only_one_rebuild_at_a_time_per_dossier(client: TestClient, dispatched) -> None:
    analyse, dossier = make_dossier(client, strategy="classique", embedding_model="e5")
    assert start(client, dossier).status_code == 202

    second = start(client, dossier)

    assert second.status_code == 409 and second.json()["detail"]["code"] == "reconstruction_en_cours"
    assert len(dispatched) == 1


def test_unresolvable_settings_refuse_the_rebuild(client: TestClient, dispatched, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_EMBEDDING_MODEL", "")
    _, dossier = make_dossier(client)
    response = start(client, dossier)
    assert response.status_code == 422 and response.json()["detail"]["code"] == "reglages_incomplets"


def swap(client: TestClient, rebuild: dict, **extra) -> None:
    """Ce que fait le worker à la bascule : il le dit au backend, qui prend les nouveaux réglages."""
    report_rebuild(client, rebuild["id"], status="swapped", **extra)


def test_a_rebuild_goes_building_swapped_then_is_validated(client: TestClient, dispatched) -> None:
    analyse, dossier = make_dossier(client, strategy="classique", embedding_model="e5")
    first_index(client, analyse, dossier)
    force_obsolete(client, analyse, embedding_model="e5-large")
    rebuild = start(client, dossier).json()
    assert rebuild["previous_fingerprint"] is not None

    progress = report_rebuild(client, rebuild["id"], total_pages=40, done_pages=10)
    assert (progress["total_pages"], progress["done_pages"], progress["status"]) == (40, 10, "building")

    swap(client, rebuild)
    report(
        client,
        dossier,
        status="ready",
        chunk_count=40,
        fingerprint=rebuild["target_fingerprint"],
        settings={**effective(client, analyse), "embedding_model": "e5-large"},
        replace_settings=True,
    )
    state = client.get(f"/api/dossiers/{dossier}/search-index").json()
    assert state["rebuild"]["status"] == "swapped" and state["rebuild"]["swapped_at"] is not None
    assert state["fingerprint"] == rebuild["target_fingerprint"] and state["freshness"] == "current"

    validated = client.post(f"/api/dossiers/{dossier}/search-index/rebuilds/{rebuild['id']}/validate")

    assert validated.status_code == 200 and validated.json()["status"] == "finalized"
    assert validated.json()["finished_at"] is not None
    assert dispatched[-1] == ("finalize_rebuild", rebuild["id"])
    assert start(client, dossier).status_code == 409  # plus de reconstruction active : l'index est à jour


def test_rolling_back_a_swapped_rebuild_restores_the_previous_settings(client: TestClient, dispatched) -> None:
    analyse, dossier = make_dossier(client, strategy="classique", embedding_model="e5")
    first_index(client, analyse, dossier)
    previous = client.get(f"/api/dossiers/{dossier}/search-index").json()["fingerprint"]
    force_obsolete(client, analyse, embedding_model="e5-large")
    rebuild = start(client, dossier).json()
    swap(client, rebuild)
    report(
        client,
        dossier,
        status="ready",
        chunk_count=5,
        fingerprint=rebuild["target_fingerprint"],
        settings={"embedding_model": "e5-large"},
        replace_settings=True,
    )

    rolled = client.post(f"/api/dossiers/{dossier}/search-index/rebuilds/{rebuild['id']}/rollback")

    assert rolled.status_code == 200 and rolled.json()["status"] == "rolled_back"
    assert dispatched[-1] == ("rollback_rebuild", rebuild["id"])
    assert client.get(f"/api/dossiers/{dossier}/search-index").json()["fingerprint"] == previous


def test_a_rebuild_in_progress_can_be_cancelled(client: TestClient, dispatched) -> None:
    analyse, dossier = make_dossier(client, strategy="classique", embedding_model="e5")
    rebuild = start(client, dossier).json()

    rolled = client.post(f"/api/dossiers/{dossier}/search-index/rebuilds/{rebuild['id']}/rollback")

    assert rolled.json()["status"] == "rolled_back"
    assert start(client, dossier).status_code == 202  # une autre peut démarrer


def test_validation_needs_a_swapped_rebuild(client: TestClient, dispatched) -> None:
    _, dossier = make_dossier(client, strategy="classique", embedding_model="e5")
    rebuild = start(client, dossier).json()

    response = client.post(f"/api/dossiers/{dossier}/search-index/rebuilds/{rebuild['id']}/validate")

    assert response.status_code == 409 and response.json()["detail"]["code"] == "etat_incompatible"


def test_a_finished_rebuild_cannot_be_rolled_back(client: TestClient, dispatched) -> None:
    _, dossier = make_dossier(client, strategy="classique", embedding_model="e5")
    rebuild = start(client, dossier).json()
    report_rebuild(client, rebuild["id"], status="failed", error="boom")

    response = client.post(f"/api/dossiers/{dossier}/search-index/rebuilds/{rebuild['id']}/rollback")

    assert response.status_code == 409
    state = client.get(f"/api/dossiers/{dossier}/search-index").json()["rebuild"]
    assert (state["status"], state["error"]) == ("failed", "boom")


def test_a_rebuild_of_another_dossier_is_not_found(client: TestClient, dispatched) -> None:
    _, dossier = make_dossier(client, strategy="classique", embedding_model="e5")
    _, other = make_dossier(client, strategy="classique", embedding_model="e5")
    rebuild = start(client, dossier).json()

    assert client.post(f"/api/dossiers/{other}/search-index/rebuilds/{rebuild['id']}/rollback").status_code == 404
    assert client.post(f"/api/dossiers/{other}/search-index/rebuilds/{uuid.uuid4()}/validate").status_code == 404


def test_the_indexation_reads_a_rebuild_and_its_targets(client: TestClient, dispatched) -> None:
    analyse, dossier = make_dossier(client, strategy="classique", embedding_model="e5")
    rebuild = start(client, dossier).json()

    config = search_config(client, dossier)

    assert config["rebuild"]["status"] == "building"
    assert config["rebuild"]["id"] == rebuild["id"]
    assert config["rebuild_target_settings"] == effective(client, analyse)


def test_deleting_a_dossier_deletes_its_index_state(client: TestClient, dispatched) -> None:
    analyse, dossier = make_dossier(client, strategy="classique", embedding_model="e5")
    first_index(client, analyse, dossier)

    async def count(session):
        from sqlalchemy import func, select

        return (
            await session.execute(
                select(func.count())
                .select_from(DossierSearchIndex)
                .where(DossierSearchIndex.dossier_id == uuid.UUID(dossier))
            )
        ).scalar_one()

    assert run(client, count) == 1

    async def delete(session):
        from sqlalchemy import delete as sql_delete

        from app.models.dossier import Dossier

        await session.execute(sql_delete(Dossier).where(Dossier.id == uuid.UUID(dossier)))
        await session.commit()

    run(client, delete)
    assert run(client, count) == 0


# --- Reconstruction en lot d'une analyse ---


def analyse_url(analyse: str, suffix: str = "") -> str:
    return f"/api/analyses/{analyse}/search-index{suffix}"


def indexed_dossiers(client: TestClient, analyse: str, count: int) -> list[str]:
    dossiers = []
    for _ in range(count):
        dossier = client.post("/api/dossiers", json={"name": "Dossier", "analyse_id": analyse}).json()["id"]
        first_index(client, analyse, dossier)
        dossiers.append(dossier)
    return dossiers


@pytest.fixture
def dispatched_ids(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    ids: list[str] = []
    monkeypatch.setattr("app.agent.dispatch.dispatch_rebuild_index", ids.append)
    monkeypatch.setattr("app.agent.dispatch.dispatch_rollback_rebuild", lambda rebuild_id: None)
    monkeypatch.setattr("app.agent.dispatch.dispatch_finalize_rebuild", lambda rebuild_id: None)
    return ids


def make_obsolete(client: TestClient, analyse: str) -> None:
    assert (
        client.put(
            f"/api/analyses/{analyse}/search-settings", json={"strategy": "classique", "embedding_model": "nouveau"}
        ).status_code
        == 200
    )


def rebuild_of(client: TestClient, dossier: str) -> dict | None:
    return client.get(f"/api/dossiers/{dossier}/search-index").json()["rebuild"]


def test_the_batch_rebuilds_only_the_obsolete_dossiers(client: TestClient, dispatched_ids, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_MAX_PARALLEL_REBUILDS", "10")
    analyse, _ = make_dossier(client, strategy="classique", embedding_model="e5")
    old = indexed_dossiers(client, analyse, 2)
    make_obsolete(client, analyse)
    fresh = indexed_dossiers(client, analyse, 1)[0]  # indexé avec les nouveaux réglages

    response = client.post(analyse_url(analyse, "/rebuild"))

    assert response.status_code == 202, response.text
    body = response.json()
    assert (body["started"], body["queued"]) == (2, 0)
    assert all(rebuild_of(client, dossier)["status"] == "building" for dossier in old)
    assert rebuild_of(client, fresh) is None
    assert len(dispatched_ids) == 2


def test_the_batch_is_capped_and_the_rest_waits_its_turn(client: TestClient, dispatched_ids, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_MAX_PARALLEL_REBUILDS", "2")
    analyse, _ = make_dossier(client, strategy="classique", embedding_model="e5")
    dossiers = indexed_dossiers(client, analyse, 5)
    make_obsolete(client, analyse)

    body = client.post(analyse_url(analyse, "/rebuild")).json()

    assert (body["started"], body["queued"]) == (2, 3)
    assert (body["overview"]["rebuilding"], body["overview"]["queued"]) == (2, 3)
    assert sorted(rebuild_of(client, d)["status"] for d in dossiers) == ["building"] * 2 + ["queued"] * 3
    assert len(dispatched_ids) == 2


def test_a_finished_build_frees_a_place_for_the_oldest_queued_one(
    client: TestClient, dispatched_ids, monkeypatch
) -> None:
    monkeypatch.setenv("SEARCH_MAX_PARALLEL_REBUILDS", "1")
    analyse, _ = make_dossier(client, strategy="classique", embedding_model="e5")
    dossiers = indexed_dossiers(client, analyse, 3)
    make_obsolete(client, analyse)
    client.post(analyse_url(analyse, "/rebuild"))
    first = next(d for d in dossiers if rebuild_of(client, d)["status"] == "building")
    # Créées dans la même transaction, les reconstructions ont la même date : l'identifiant départage.
    queued = sorted(
        (d for d in dossiers if d != first),
        key=lambda d: (rebuild_of(client, d)["created_at"], rebuild_of(client, d)["id"]),
    )

    report_rebuild(client, rebuild_of(client, first)["id"], status="swapped")

    assert rebuild_of(client, queued[0])["status"] == "building"
    assert rebuild_of(client, queued[1])["status"] == "queued"
    assert dispatched_ids[-1] == rebuild_of(client, queued[0])["id"]


def test_a_failed_build_also_frees_its_place(client: TestClient, dispatched_ids, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_MAX_PARALLEL_REBUILDS", "1")
    analyse, _ = make_dossier(client, strategy="classique", embedding_model="e5")
    dossiers = indexed_dossiers(client, analyse, 2)
    make_obsolete(client, analyse)
    client.post(analyse_url(analyse, "/rebuild"))
    first = next(d for d in dossiers if rebuild_of(client, d)["status"] == "building")
    second = next(d for d in dossiers if d != first)

    report_rebuild(client, rebuild_of(client, first)["id"], status="failed", error="x")

    assert rebuild_of(client, second)["status"] == "building"


def test_cancelling_a_running_build_frees_its_place_and_a_queued_one_can_be_cancelled(
    client: TestClient, dispatched_ids, monkeypatch
) -> None:
    monkeypatch.setenv("SEARCH_MAX_PARALLEL_REBUILDS", "1")
    analyse, _ = make_dossier(client, strategy="classique", embedding_model="e5")
    dossiers = indexed_dossiers(client, analyse, 3)
    make_obsolete(client, analyse)
    client.post(analyse_url(analyse, "/rebuild"))
    running = next(d for d in dossiers if rebuild_of(client, d)["status"] == "building")
    waiting = [d for d in dossiers if d != running]

    cancel = client.post(f"/api/dossiers/{running}/search-index/rebuilds/{rebuild_of(client, running)['id']}/rollback")
    assert cancel.json()["status"] == "rolled_back"
    promoted = [d for d in waiting if rebuild_of(client, d)["status"] == "building"]
    assert len(promoted) == 1

    queued = next(d for d in waiting if d not in promoted)
    client.post(f"/api/dossiers/{queued}/search-index/rebuilds/{rebuild_of(client, queued)['id']}/rollback")
    assert rebuild_of(client, queued)["status"] == "rolled_back"


def test_the_batch_skips_dossiers_already_being_rebuilt_and_is_repeatable(
    client: TestClient, dispatched_ids, monkeypatch
) -> None:
    monkeypatch.setenv("SEARCH_MAX_PARALLEL_REBUILDS", "10")
    analyse, _ = make_dossier(client, strategy="classique", embedding_model="e5")
    indexed_dossiers(client, analyse, 2)
    make_obsolete(client, analyse)

    assert client.post(analyse_url(analyse, "/rebuild")).json()["started"] == 2
    again = client.post(analyse_url(analyse, "/rebuild")).json()

    assert (again["started"], again["queued"]) == (0, 0)
    assert len(dispatched_ids) == 2


def test_an_index_in_error_is_rebuilt_even_with_unchanged_settings(
    client: TestClient, dispatched_ids, monkeypatch
) -> None:
    monkeypatch.setenv("SEARCH_MAX_PARALLEL_REBUILDS", "10")
    analyse, dossier = make_dossier(client, strategy="classique", embedding_model="e5")
    first_index(client, analyse, dossier, status="error", error="boom")

    assert client.post(analyse_url(analyse, "/rebuild")).json()["started"] == 1


def test_the_batch_needs_resolvable_settings(client: TestClient, dispatched_ids, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_EMBEDDING_MODEL", "")
    analyse, _ = make_dossier(client)
    response = client.post(analyse_url(analyse, "/rebuild"))
    assert response.status_code == 422 and response.json()["detail"]["code"] == "reglages_incomplets"


def test_the_overview_counts_every_state(client: TestClient, dispatched_ids, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_MAX_PARALLEL_REBUILDS", "1")
    analyse, _ = make_dossier(client, strategy="classique", embedding_model="e5")
    indexed_dossiers(client, analyse, 3)
    client.post("/api/dossiers", json={"name": "Jamais indexé", "analyse_id": analyse})
    make_obsolete(client, analyse)
    client.post(analyse_url(analyse, "/rebuild"))

    overview = client.get(analyse_url(analyse)).json()

    assert overview["dossiers"] == 5 and overview["indexed"] == 3 and overview["obsolete"] == 3
    assert (overview["rebuilding"], overview["queued"], overview["to_validate"]) == (1, 2, 0)
