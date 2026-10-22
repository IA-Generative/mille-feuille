"""Tests de la migration des validations de prédiction vers l'analyse de dossier (issue #120).

Deux volets :
- la route ``PUT .../predictions/{id}/validations`` garde son contrat mais
  écrit dans l'analyse de dossier (versions d'instructeur) ;
- la migration de données (``backfill``) recopie l'historique existant de
  ``prediction_validations``, sans perte et de façon idempotente."""

import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import async_session_factory
from app.models.dossier_analysis import DossierAnalysis, DossierAnalysisStatus

INTERNAL = {"X-App-Token": "dev-only-worker-token-not-for-prod"}
_MIGRATION = next(Path(__file__).parent.parent.joinpath("migrations/versions").glob("*_3c4d5e6f7a8b_*.py"))
_spec = importlib.util.spec_from_file_location("migrate_prediction_validations", _MIGRATION)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


@pytest.fixture(autouse=True)
def _no_celery_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("dispatch_classification", "dispatch_entity_extraction", "dispatch_agent_execution"):
        monkeypatch.setattr(f"app.routers.dossiers.{name}", lambda dossier_id, *args, **kwargs: None)


def _dossier(client: TestClient) -> tuple[str, str, dict[str, Any]]:
    analyse_id = client.post("/api/analyses", json={"name": "Analyse validations", "description": "t"}).json()["id"]
    dossier_id = client.post("/api/dossiers", json={"name": "Dossier validations", "analyse_id": analyse_id}).json()[
        "id"
    ]
    document = client.post(
        f"/api/dossiers/{dossier_id}/documents", files=[("files", ("cni.pdf", b"x", "application/pdf"))]
    ).json()["documents"][0]
    page = client.post(
        f"/api/internal/documents/{document['id']}/pages",
        json={"page_number": 2, "content": "Nom : Dupond"},
        headers=INTERNAL,
    ).json()
    return dossier_id, document["id"], page


def _prediction(client: TestClient, page_id: str, **fields: Any) -> dict[str, Any]:
    body = {"kind": "entity", "name": "nom", "value": "Dupond", "confidence": 0.8, **fields}
    return client.post(f"/api/internal/pages/{page_id}/predictions", json=body, headers=INTERNAL).json()


def _validate(client: TestClient, ids: tuple[str, str, str, str], **body: Any):
    dossier_id, document_id, page_id, prediction_id = ids
    return client.put(
        f"/api/dossiers/{dossier_id}/documents/{document_id}/pages/{page_id}/predictions/{prediction_id}/validations",
        json=body,
    )


def _sql(client: TestClient, statement: str, **params: Any) -> Any:
    async def run() -> Any:
        async with async_session_factory() as session:
            result = await session.execute(text(statement), params)
            rows = result.mappings().all() if result.returns_rows else None
            await session.commit()
            return rows

    return client.portal.call(run)


def _legacy_count(client: TestClient, prediction_id: str) -> int:
    rows = _sql(client, "SELECT count(*) AS n FROM prediction_validations WHERE prediction_id = :p", p=prediction_id)
    return rows[0]["n"]


def _backfill(client: TestClient) -> dict[str, int]:
    async def run() -> dict[str, int]:
        async with async_session_factory() as session:
            stats = await session.run_sync(lambda sync_session: migration.backfill(sync_session.connection()))
            await session.commit()
            return stats

    return client.portal.call(run)


def _analysis_elements(client: TestClient, dossier_id: str) -> list[dict[str, Any]]:
    return client.get(f"/api/dossiers/{dossier_id}/analyse-dossier").json()["elements"]


def _versions(client: TestClient, dossier_id: str, element: dict[str, Any]) -> list[dict[str, Any]]:
    return client.get(
        f"/api/dossiers/{dossier_id}/analyses-dossier/{element['analysis_id']}/elements/{element['id']}/versions"
    ).json()


# --- La route écrit dans l'analyse de dossier, contrat inchangé ---


def test_validation_keeps_its_contract_and_writes_an_instructor_version(client: TestClient) -> None:
    dossier_id, document_id, page = _dossier(client)
    prediction = _prediction(client, page["id"])
    ids = (dossier_id, document_id, page["id"], prediction["id"])

    response = _validate(client, ids, status="corrigé", corrected_value="Dupont")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "corrigé"
    assert body["corrected_value"] == "Dupont"
    assert body["validator_user_id"]
    assert body["bounding_box"] is None
    # Rien n'est écrit dans l'ancienne table.
    assert _legacy_count(client, prediction["id"]) == 0
    # L'analyse de dossier porte la décision, à côté de la prédiction du modèle.
    [element] = _analysis_elements(client, dossier_id)
    assert element["source_prediction_id"] == prediction["id"]
    assert element["retained_version"]["value"] == {"value": "Dupont"}
    assert element["retained_version"]["origin"] == "instructor"
    assert element["retained_version"]["validation_status"] == "corrigé"
    assert element["latest_model_version"]["value"] == {"value": "Dupond"}
    assert body["id"] == element["retained_version"]["id"]


def test_validations_are_listed_on_the_prediction_in_order(client: TestClient) -> None:
    dossier_id, document_id, page = _dossier(client)
    prediction = _prediction(client, page["id"])
    ids = (dossier_id, document_id, page["id"], prediction["id"])
    _validate(client, ids, status="validé")
    _validate(client, ids, status="corrigé", corrected_value="Dupont")

    dossier = client.get(f"/api/dossiers/{dossier_id}").json()
    [listed] = dossier["documents"][0]["pages"][0]["predictions"]
    assert [v["status"] for v in listed["validations"]] == ["validé", "corrigé"]
    assert [v["corrected_value"] for v in listed["validations"]] == [None, "Dupont"]


def test_validated_prediction_confirms_the_value(client: TestClient) -> None:
    dossier_id, document_id, page = _dossier(client)
    prediction = _prediction(client, page["id"])
    _validate(client, (dossier_id, document_id, page["id"], prediction["id"]), status="validé")

    [element] = _analysis_elements(client, dossier_id)
    assert element["retained_version"]["value"] == {"value": "Dupond"}
    assert element["retained_version"]["validation_status"] == "validé"
    assert element["needs_review"] is False


def test_rejected_prediction_is_kept_and_flagged_for_review(client: TestClient) -> None:
    dossier_id, document_id, page = _dossier(client)
    prediction = _prediction(client, page["id"])
    response = _validate(client, (dossier_id, document_id, page["id"], prediction["id"]), status="rejeté")

    assert response.json()["status"] == "rejeté"
    [element] = _analysis_elements(client, dossier_id)
    assert element["retained_version"]["validation_status"] == "rejeté"
    assert element["needs_review"] is True
    assert "rejetée" in element["review_reason"].lower()


def test_corrected_zone_is_a_new_bounding_box(client: TestClient) -> None:
    dossier_id, document_id, page = _dossier(client)
    prediction = _prediction(client, page["id"])
    zone = {"x_min": 0.1, "y_min": 0.2, "x_max": 0.5, "y_max": 0.4}
    response = _validate(
        client,
        (dossier_id, document_id, page["id"], prediction["id"]),
        status="corrigé",
        corrected_value="X",
        bounding_box=zone,
    )
    box = response.json()["bounding_box"]
    assert (box["x_min"], box["y_max"]) == (0.1, 0.4)
    assert box["document_page_id"] == page["id"]
    [element] = _analysis_elements(client, dossier_id)
    assert element["retained_version"]["bounding_box_id"] == box["id"]


def test_classification_correction_changes_its_label(client: TestClient) -> None:
    dossier_id, document_id, page = _dossier(client)
    prediction = _prediction(client, page["id"], kind="label", name="CNI", value="CNI")
    response = _validate(
        client, (dossier_id, document_id, page["id"], prediction["id"]), status="corrigé", corrected_value="Passeport"
    )
    assert response.json()["corrected_value"] == "Passeport"
    [element] = _analysis_elements(client, dossier_id)
    assert element["kind"] == "classification"
    assert element["retained_version"]["value"] == {"label": "Passeport"}


def test_validation_uses_the_element_of_the_running_analysis(client: TestClient) -> None:
    dossier_id, document_id, page = _dossier(client)
    client.post(f"/api/dossiers/{dossier_id}/launch")
    unit = client.post(
        f"/api/internal/dossiers/{dossier_id}/analysis-units", json={"kind": "extraction"}, headers=INTERNAL
    ).json()
    prediction = _prediction(client, page["id"], unit_id=unit["id"])
    _validate(client, (dossier_id, document_id, page["id"], prediction["id"]), status="validé")

    [element] = _analysis_elements(client, dossier_id)
    assert element["unit_id"] == unit["id"]
    assert [v["origin"] for v in _versions(client, dossier_id, element)] == ["model", "instructor"]
    assert len(client.get(f"/api/dossiers/{dossier_id}/analyses-dossier").json()) == 1


def test_validation_on_a_frozen_analysis_is_refused(client: TestClient) -> None:
    dossier_id, document_id, page = _dossier(client)
    prediction = _prediction(client, page["id"])
    ids = (dossier_id, document_id, page["id"], prediction["id"])
    _validate(client, ids, status="validé")
    [element] = _analysis_elements(client, dossier_id)

    async def freeze() -> None:
        async with async_session_factory() as session:
            row = await session.get(DossierAnalysis, uuid.UUID(element["analysis_id"]))
            row.status = DossierAnalysisStatus.FIGEE
            await session.commit()

    client.portal.call(freeze)
    assert _validate(client, ids, status="rejeté").status_code == 409


def test_validation_of_an_unknown_prediction_is_404(client: TestClient) -> None:
    dossier_id, document_id, page = _dossier(client)
    response = _validate(client, (dossier_id, document_id, page["id"], str(uuid.uuid4())), status="validé")
    assert response.status_code == 404


# --- Migration de l'historique existant ---


def _legacy(
    client: TestClient, prediction_id: str, rows: list[tuple[str, str | None, str]], start: datetime
) -> list[str]:
    """Insère des lignes dans l'ancienne table (statut, valeur corrigée, auteur)."""
    ids = []
    for index, (status, corrected, author) in enumerate(rows):
        validation_id = str(uuid.uuid4())
        ids.append(validation_id)
        _sql(
            client,
            "INSERT INTO prediction_validations (id, prediction_id, validator_user_id, status, corrected_value, "
            "created_at) VALUES (:id, :p, :u, CAST(:s AS prediction_validation_status), :c, :t)",
            id=validation_id,
            p=prediction_id,
            u=author,
            s=status,
            c=corrected,
            t=start + timedelta(minutes=index),
        )
    return ids


def test_backfill_migrates_existing_validations_without_loss(client: TestClient) -> None:
    dossier_id, _, page = _dossier(client)
    prediction = _prediction(client, page["id"])
    start = datetime(2026, 1, 1, tzinfo=UTC)
    legacy_ids = _legacy(
        client,
        prediction["id"],
        [("VALIDATED", None, "alice"), ("CORRECTED", "Dupont", "bob"), ("REJECTED", None, "carol")],
        start,
    )

    stats = _backfill(client)

    assert stats["versions"] >= 3
    [element] = _analysis_elements(client, dossier_id)
    assert element["source_prediction_id"] == prediction["id"]
    versions = _versions(client, dossier_id, element)
    # Version du modèle, puis une version d'instructeur par validation, dans l'ordre.
    assert [v["version_number"] for v in versions] == [1, 2, 3, 4]
    assert [v["origin"] for v in versions] == ["model", "instructor", "instructor", "instructor"]
    assert [v["validation_status"] for v in versions] == [None, "validé", "corrigé", "rejeté"]
    assert [v["author_id"] for v in versions[1:]] == ["alice", "bob", "carol"]
    assert [v["source_id"] for v in versions[1:]] == legacy_ids
    assert {v["source_type"] for v in versions[1:]} == {"prediction_validation"}
    # Le rejet ne perd pas la valeur corrigée précédente ; l'élément est « à revoir ».
    assert [v["value"] for v in versions] == [
        {"value": "Dupond"},
        {"value": "Dupond"},
        {"value": "Dupont"},
        {"value": "Dupont"},
    ]
    assert element["retained_version"]["id"] == versions[-1]["id"]
    assert element["latest_model_version"]["id"] == versions[0]["id"]
    assert element["needs_review"] is True
    # L'ancienne table n'est pas modifiée.
    assert _legacy_count(client, prediction["id"]) == 3
    # Et l'API de lecture des prédictions renvoie le même historique qu'avant.
    dossier = client.get(f"/api/dossiers/{dossier_id}").json()
    [listed] = dossier["documents"][0]["pages"][0]["predictions"]
    assert [v["status"] for v in listed["validations"]] == ["validé", "corrigé", "rejeté"]
    assert listed["validations"][1]["corrected_value"] == "Dupont"
    assert [v["validator_user_id"] for v in listed["validations"]] == ["alice", "bob", "carol"]


def test_backfill_is_idempotent(client: TestClient) -> None:
    dossier_id, _, page = _dossier(client)
    prediction = _prediction(client, page["id"])
    _legacy(client, prediction["id"], [("VALIDATED", None, "alice")], datetime(2026, 1, 1, tzinfo=UTC))

    _backfill(client)
    second = _backfill(client)

    assert second == {"analyses": 0, "elements": 0, "versions": 0}
    [element] = _analysis_elements(client, dossier_id)
    assert len(_versions(client, dossier_id, element)) == 2


def test_backfill_keeps_the_corrected_zone(client: TestClient) -> None:
    dossier_id, document_id, page = _dossier(client)
    prediction = _prediction(client, page["id"])
    box = client.post(
        f"/api/internal/pages/{page['id']}/bounding-boxes",
        json={"x_min": 0.1, "y_min": 0.1, "x_max": 0.9, "y_max": 0.5},
        headers=INTERNAL,
    ).json()
    _sql(
        client,
        "INSERT INTO prediction_validations (id, prediction_id, bounding_box_id, validator_user_id, status, "
        "corrected_value) VALUES (:id, :p, :b, 'alice', CAST('CORRECTED' AS prediction_validation_status), 'Dupont')",
        id=str(uuid.uuid4()),
        p=prediction["id"],
        b=box["id"],
    )

    _backfill(client)

    [element] = _analysis_elements(client, dossier_id)
    assert element["retained_version"]["bounding_box_id"] == box["id"]
    dossier = client.get(f"/api/dossiers/{dossier_id}").json()
    [listed] = dossier["documents"][0]["pages"][0]["predictions"]
    assert listed["validations"][0]["bounding_box"]["id"] == box["id"]


def test_backfill_creates_an_element_for_a_prediction_without_validation(client: TestClient) -> None:
    dossier_id, _, page = _dossier(client)
    prediction = _prediction(client, page["id"], kind="label", name="CNI", value="CNI", confidence=0.9)

    _backfill(client)

    [element] = _analysis_elements(client, dossier_id)
    assert element["kind"] == "classification"
    assert element["source_prediction_id"] == prediction["id"]
    assert element["first_page_number"] == 2
    assert element["retained_version"]["value"] == {"label": "CNI"}
    assert element["retained_version"]["confidence"] == 0.9
    analysis = client.get(f"/api/dossiers/{dossier_id}/analyse-dossier").json()
    assert analysis["analyse_version"] == migration.BACKFILL_MARKER


def test_backfill_analysis_never_becomes_the_current_one(client: TestClient) -> None:
    dossier_id, _, page = _dossier(client)
    # Une exécution plus récente existe déjà (sans élément pour la prédiction ancienne).
    prediction = _prediction(client, page["id"])
    client.post(f"/api/dossiers/{dossier_id}/launch")
    newer = client.get(f"/api/dossiers/{dossier_id}/analyse-dossier").json()
    assert newer["sequence"] == 1

    _backfill(client)

    analyses = client.get(f"/api/dossiers/{dossier_id}/analyses-dossier").json()
    assert [a["sequence"] for a in analyses] == [1, 0]
    assert client.get(f"/api/dossiers/{dossier_id}/analyse-dossier").json()["id"] == newer["id"]
    assert prediction["id"]


def test_backfill_appends_to_an_existing_element(client: TestClient) -> None:
    """Prédiction qui a déjà un élément (créée après #125) mais dont la
    validation a été faite dans l'ancienne table : on ajoute la validation."""
    dossier_id, _, page = _dossier(client)
    client.post(f"/api/dossiers/{dossier_id}/launch")
    unit = client.post(
        f"/api/internal/dossiers/{dossier_id}/analysis-units", json={"kind": "extraction"}, headers=INTERNAL
    ).json()
    prediction = _prediction(client, page["id"], unit_id=unit["id"])
    _legacy(client, prediction["id"], [("CORRECTED", "Dupont", "alice")], datetime(2026, 1, 1, tzinfo=UTC))

    stats = _backfill(client)

    assert stats["versions"] >= 1
    [element] = _analysis_elements(client, dossier_id)
    assert element["unit_id"] == unit["id"]
    assert element["retained_version"]["value"] == {"value": "Dupont"}
    assert element["latest_model_version"]["value"] == {"value": "Dupond"}
    assert [v["version_number"] for v in _versions(client, dossier_id, element)] == [1, 2]
    assert len(client.get(f"/api/dossiers/{dossier_id}/analyses-dossier").json()) == 1


def test_backfill_ignores_predictions_without_a_page(client: TestClient) -> None:
    _, _, page = _dossier(client)
    prediction = _prediction(client, page["id"])
    _legacy(client, prediction["id"], [("VALIDATED", None, "alice")], datetime(2026, 1, 1, tzinfo=UTC))
    _sql(client, "DELETE FROM prediction_pages WHERE prediction_id = :p", p=prediction["id"])

    _backfill(client)  # ne lève pas : le comptage ignore ces prédictions

    rows = _sql(
        client, "SELECT count(*) AS n FROM analysis_elements WHERE source_prediction_id = :p", p=prediction["id"]
    )
    assert rows[0]["n"] == 0
