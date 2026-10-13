"""Verdicts des appelants et métriques des runs éphémères : condensé non sensible, GET /metrics, rétention."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.connectors import s3_connector
from app.db import async_session_factory
from app.models.document_page import PredictionKind, PredictionSource
from app.models.ephemeral_feedback import EphemeralFeedback, EphemeralVerdict
from app.models.ephemeral_run_metrics import EphemeralRunMetrics
from app.repositories.ephemeral_repository import EphemeralRepository
from app.services import ephemeral_metrics
from app.tasks import run_purge

INTERNAL = {"X-App-Token": "dev-only-worker-token-not-for-prod"}
FILE = [("file", ("cni.pdf", b"fake-bytes", "application/pdf"))]
LABELS = '[{"name": "CNI", "definition": "d"}, {"name": "RIB", "definition": "d"}]'
ENTITIES = '[{"name": "nom", "type": "texte"}]'


@pytest.fixture(autouse=True)
def _no_s3_nor_celery(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.routers.ephemeral.s3_connector.upload", lambda *args, **kwargs: None)
    for name in (
        "dispatch_text_extraction",
        "dispatch_classification",
        "dispatch_entity_extraction",
        "dispatch_agent_execution",
    ):
        monkeypatch.setattr(f"app.routers.ephemeral.{name}", lambda *args, **kwargs: None)


def _page(client: TestClient, run_id: str, page_number: int = 1) -> str:
    document_id = client.get(f"/api/ephemeral/runs/{run_id}").json()["documents"][0]["id"]
    return client.post(
        f"/api/internal/documents/{document_id}/pages",
        json={"page_number": page_number, "content": "texte secret"},
        headers=INTERNAL,
    ).json()["id"]


def _predict(client: TestClient, page_id: str, kind: str, name: str, value: str, source: str, confidence: float) -> str:
    response = client.post(
        f"/api/internal/pages/{page_id}/predictions",
        json={"kind": kind, "name": name, "value": value, "source": source, "confidence": confidence},
        headers=INTERNAL,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _classified_run(client: TestClient) -> tuple[str, dict[str, str]]:
    """Un run de classification avec, sur la page 1, un label textuel et un label visuel (et une entité)."""
    run_id = client.post("/api/ephemeral/classifications", files=FILE, data={"labels": LABELS}).json()["run_id"]
    page = _page(client, run_id)
    ids = {
        "textual": _predict(client, page, "label", "CNI", "CNI", "textual", 0.9),
        "visual": _predict(client, page, "label", "RIB", "RIB", "visual", 0.6),
        "entity": _predict(client, page, "entity", "nom", "Dupont Jean", "gliner", 0.8),
    }
    return run_id, ids


def test_verdicts_are_stored_and_replaced_by_the_latest(client: TestClient) -> None:
    run_id, ids = _classified_run(client)
    url = f"/api/ephemeral/runs/{run_id}/feedback"

    first = client.post(url, json={"items": [{"prediction_id": ids["textual"], "verdict": "correct"}]})
    assert first.status_code == 200
    assert first.json()[0]["name"] == "CNI" and first.json()[0]["source"] == "textual"

    client.post(
        url, json={"items": [{"prediction_id": ids["textual"], "verdict": "incorrect", "expected_name": "RIB"}]}
    )
    stored = client.get(url).json()
    assert [(f["verdict"], f["expected_name"]) for f in stored] == [("incorrect", "RIB")]


def test_stored_feedback_never_contains_the_extracted_value_nor_the_page_text(client: TestClient) -> None:
    run_id, ids = _classified_run(client)
    client.post(
        f"/api/ephemeral/runs/{run_id}/feedback",
        json={"items": [{"prediction_id": ids["entity"], "verdict": "correct"}]},
    )
    metrics = client.get(f"/api/ephemeral/runs/{run_id}/metrics")
    everything = metrics.text + client.get(f"/api/ephemeral/runs/{run_id}/feedback").text
    assert "Dupont" not in everything and "texte secret" not in everything and "cni.pdf" not in everything


def test_unknown_prediction_and_misplaced_expected_name_are_rejected(client: TestClient) -> None:
    run_id, ids = _classified_run(client)
    url = f"/api/ephemeral/runs/{run_id}/feedback"
    assert (
        client.post(url, json={"items": [{"prediction_id": str(uuid.uuid4()), "verdict": "correct"}]}).status_code
        == 422
    )
    assert (
        client.post(
            url, json={"items": [{"prediction_id": ids["entity"], "verdict": "incorrect", "expected_name": "autre"}]}
        ).status_code
        == 422
    )
    assert (
        client.post(
            url, json={"items": [{"prediction_id": ids["textual"], "verdict": "correct", "expected_name": "RIB"}]}
        ).status_code
        == 422
    )
    assert client.post(url, json={"items": []}).status_code == 422


def test_run_metrics_report_volumes_agreement_and_quality(client: TestClient) -> None:
    run_id, ids = _classified_run(client)
    client.post(
        f"/api/ephemeral/runs/{run_id}/feedback",
        json={
            "items": [
                {"prediction_id": ids["textual"], "verdict": "correct"},
                {"prediction_id": ids["visual"], "verdict": "incorrect", "expected_name": "CNI"},
            ]
        },
    )

    metrics = client.get(f"/api/ephemeral/runs/{run_id}/metrics").json()

    assert metrics["page_count"] == 1 and metrics["status"] == "en_cours"
    volume = {(v["kind"], v["source"]): v for v in metrics["volume"]}
    assert volume[("label", "textual")]["avg_confidence"] == 0.9
    assert volume[("entity", "gliner")]["predictions"] == 1
    # CNI (texte) contre RIB (visuel) sur la même page : pas d'accord.
    assert metrics["classification_agreement"] == {"pages_compared": 1, "pages_agreeing": 0, "agreement_rate": 0.0}
    quality = {q["source"]: q for q in metrics["quality"]}
    assert quality["textual"]["precision"] == 1.0 and quality["visual"]["precision"] == 0.0
    assert metrics["confusion"] == [{"source": "visual", "predicted": "RIB", "expected": "CNI", "count": 1}]


def _by_name(metrics: dict) -> dict:
    return {(q["source"], q["name"]): q for q in metrics["by_name"]}


def test_global_metrics_aggregate_the_callers_runs_and_filter(client: TestClient) -> None:
    # La base de test est partagée : on mesure ce que ce test ajoute, pas des valeurs absolues.
    before = client.get("/api/ephemeral/metrics").json()
    run_id, ids = _classified_run(client)
    client.post(
        f"/api/ephemeral/runs/{run_id}/feedback",
        json={
            "items": [
                {"prediction_id": ids["textual"], "verdict": "correct"},
                {"prediction_id": ids["entity"], "verdict": "incorrect"},
            ]
        },
    )

    after = client.get("/api/ephemeral/metrics").json()
    assert after["runs"] == before["runs"] + 1
    assert after["pages"] == before["pages"] + 1
    cni_before = _by_name(before).get(("textual", "CNI"), {"correct": 0})["correct"]
    nom_before = _by_name(before).get(("gliner", "nom"), {"incorrect": 0})["incorrect"]
    assert _by_name(after)[("textual", "CNI")]["correct"] == cni_before + 1
    assert _by_name(after)[("gliner", "nom")]["incorrect"] == nom_before + 1

    only_entities = client.get("/api/ephemeral/metrics", params={"kind": "entity"}).json()
    assert {q["kind"] for q in only_entities["quality"]} == {"entity"}
    only_visual = client.get("/api/ephemeral/metrics", params={"source": "visual"}).json()
    assert {q["source"] for q in only_visual["quality"]} <= {"visual"}
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    assert client.get("/api/ephemeral/metrics", params={"since": future}).json()["quality"] == []


def test_metrics_and_feedback_are_private_to_their_owner(client: TestClient) -> None:
    run_id, _ = _classified_run(client)
    other = client.post("/api/app-tokens", json={"name": "voisin"}).json()["token"]
    headers = {"X-App-Token": other}
    assert client.get(f"/api/ephemeral/runs/{run_id}/metrics", headers=headers).status_code == 404
    assert client.get(f"/api/ephemeral/runs/{run_id}/feedback", headers=headers).status_code == 404
    assert client.get(f"/api/ephemeral/runs/{uuid.uuid4()}/metrics").status_code == 404
    assert client.get("/api/ephemeral/metrics", headers=headers).json()["runs"] == 0


def test_deleting_the_metrics_of_a_run_removes_its_verdicts(client: TestClient) -> None:
    run_id, ids = _classified_run(client)
    client.post(
        f"/api/ephemeral/runs/{run_id}/feedback",
        json={"items": [{"prediction_id": ids["textual"], "verdict": "correct"}]},
    )

    assert client.delete(f"/api/ephemeral/runs/{run_id}/metrics").status_code == 204
    assert client.delete(f"/api/ephemeral/runs/{run_id}/metrics").status_code == 404
    assert client.get(f"/api/ephemeral/runs/{run_id}/feedback").json() == []


def test_compact_views_expose_prediction_ids_to_give_verdicts_on(client: TestClient) -> None:
    run_id, ids = _classified_run(client)
    labels = client.get(f"/api/ephemeral/classifications/{run_id}").json()["documents"][0]["pages"][0]["labels"]
    assert {label["prediction_id"] for label in labels} == {ids["textual"], ids["visual"]}
    entities = client.get(f"/api/ephemeral/extractions/{run_id}").json()["documents"][0]["pages"][0]["entities"]
    assert [e["prediction_id"] for e in entities] == [ids["entity"]]


async def _delete_result(run_id: uuid.UUID) -> None:
    async with async_session_factory() as db:
        await EphemeralRepository(db).delete_result(run_id)


def test_digest_and_verdicts_outlive_the_dossier_and_the_kept_result(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(s3_connector, "delete", lambda *args, **kwargs: None)
    monkeypatch.setattr(s3_connector, "delete_prefix", lambda *args, **kwargs: 0)
    run_id, ids = _classified_run(client)

    for step in client.get(f"/api/ephemeral/runs/{run_id}").json()["execution_steps"]:
        client.post(
            f"/api/internal/execution-steps/{step['id']}/complete",
            json={"status": "terminé", "output": "ok"},
            headers=INTERNAL,
        )
    assert client.get(f"/api/ephemeral/runs/{run_id}").json()["status"] == "terminé"  # dossier supprimé, résultat gardé

    client.portal.call(_delete_result, uuid.UUID(run_id))  # le résultat expire à son tour
    assert client.get(f"/api/ephemeral/runs/{run_id}").status_code == 404

    # Le condensé non sensible reste : métriques lisibles et verdicts encore possibles.
    metrics = client.get(f"/api/ephemeral/runs/{run_id}/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["status"] == "terminé" and metrics.json()["duration_seconds"] is not None
    assert {v["source"] for v in metrics.json()["volume"]} == {"textual", "visual", "gliner"}
    late = client.post(
        f"/api/ephemeral/runs/{run_id}/feedback",
        json={"items": [{"prediction_id": ids["textual"], "verdict": "correct"}]},
    )
    assert late.status_code == 200
    assert client.get(f"/api/ephemeral/runs/{run_id}/metrics").json()["quality"][0]["correct"] == 1


async def _backdate_metrics(run_id: uuid.UUID, days: int) -> None:
    async with async_session_factory() as db:
        old = datetime.now(UTC) - timedelta(days=days)
        await db.execute(update(EphemeralRunMetrics).where(EphemeralRunMetrics.run_id == run_id).values(created_at=old))
        await db.execute(update(EphemeralFeedback).where(EphemeralFeedback.run_id == run_id).values(created_at=old))
        await db.commit()


async def _stored(run_id: uuid.UUID) -> tuple[bool, int]:
    """(condensé présent ?, nombre de verdicts) pour un run, tous appelants confondus."""
    async with async_session_factory() as db:
        digest = await EphemeralRepository(db).get_run_metrics(run_id) is not None
        verdicts = (
            await db.execute(
                select(func.count()).select_from(EphemeralFeedback).where(EphemeralFeedback.run_id == run_id)
            )
        ).scalar_one()
        return digest, verdicts


def test_the_retention_purge_deletes_old_digests_and_verdicts_only(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EPHEMERAL_METRICS_RETENTION_DAYS", "30")
    old_run, old_ids = _classified_run(client)
    recent_run, recent_ids = _classified_run(client)
    for run_id, ids in ((old_run, old_ids), (recent_run, recent_ids)):
        client.post(
            f"/api/ephemeral/runs/{run_id}/feedback",
            json={"items": [{"prediction_id": ids["textual"], "verdict": "correct"}]},
        )
    assert client.portal.call(_stored, uuid.UUID(old_run)) == (True, 1)
    client.portal.call(_backdate_metrics, uuid.UUID(old_run), 31)

    summary = client.portal.call(run_purge)

    assert summary["purged_metrics"] >= 2  # le condensé et le verdict du vieux run
    assert client.portal.call(_stored, uuid.UUID(old_run)) == (False, 0)
    assert client.portal.call(_stored, uuid.UUID(recent_run)) == (True, 1)


# --- Calculs (sans base) ---


def _row(
    source: str, name: str, verdict: str, *, kind: str = "label", confidence: float = 0.8, expected: str | None = None
):
    return SimpleNamespace(
        kind=PredictionKind(kind),
        source=PredictionSource(source),
        name=name,
        verdict=EphemeralVerdict(verdict),
        confidence=confidence,
        expected_name=expected,
    )


def test_quality_counts_precision_and_confidence_per_method() -> None:
    rows = [
        _row("textual", "CNI", "correct", confidence=0.9),
        _row("textual", "CNI", "correct", confidence=0.7),
        _row("textual", "RIB", "incorrect", confidence=0.5),
        _row("visual", "CNI", "incorrect", confidence=0.4),
    ]
    quality = {q.source.value: q for q in ephemeral_metrics.quality_by_source(rows)}
    assert (quality["textual"].evaluated, quality["textual"].correct, quality["textual"].precision) == (3, 2, 0.6667)
    assert quality["textual"].avg_confidence_correct == 0.8
    assert quality["textual"].avg_confidence_incorrect == 0.5
    assert quality["visual"].precision == 0.0 and quality["visual"].avg_confidence_correct is None


def test_confusion_only_counts_incorrect_labels_with_an_expected_name() -> None:
    rows = [
        _row("textual", "RIB", "incorrect", expected="CNI"),
        _row("textual", "RIB", "incorrect", expected="CNI"),
        _row("textual", "RIB", "incorrect"),
        _row("textual", "RIB", "correct"),
        _row("gliner", "nom", "incorrect", kind="entity"),
    ]
    assert [(c.predicted, c.expected, c.count) for c in ephemeral_metrics.confusion(rows)] == [("RIB", "CNI", 2)]


def test_agreement_does_not_mix_pages_of_different_documents_or_runs() -> None:
    def label(source: str, name: str, document: int, run: str = "r1") -> dict:
        return {"kind": "label", "source": source, "name": name, "page_number": 1, "document": document, "run": run}

    predictions = [
        label("textual", "CNI", 0),
        label("visual", "CNI", 0),  # d'accord
        label("textual", "CNI", 1),
        label("visual", "RIB", 1),  # même page 1, autre document : pas d'accord
        label("textual", "CNI", 0, run="r2"),  # pas de visuel : non comparée
    ]
    result = ephemeral_metrics.agreement(predictions)
    assert (result.pages_compared, result.pages_agreeing, result.agreement_rate) == (2, 1, 0.5)
