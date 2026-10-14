import json
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.models.dossier import DossierStatus
from app.services.ephemeral_results import to_classification_out, to_extraction_out


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


FILE = [("file", ("cni.pdf", b"fake-bytes", "application/pdf"))]
LABELS = json.dumps([{"name": "CNI", "definition": "Carte d'identité"}, {"name": "RIB", "definition": "Relevé"}])
ENTITIES = json.dumps([{"name": "nom", "definition": "Nom de famille", "type": "texte"}])


def test_classification_in_one_call_then_read_pending_result(client: TestClient) -> None:
    created = client.post("/api/ephemeral/classifications", files=FILE, data={"labels": LABELS, "multi_label": "true"})
    assert created.status_code == 201
    run_id = created.json()["run_id"]

    result = client.get(f"/api/ephemeral/classifications/{run_id}")
    assert result.status_code == 200
    body = result.json()
    assert body["run_id"] == run_id
    assert body["status"] == "en_cours"
    assert body["error"] is None
    assert [d["name"] for d in body["documents"]] == ["cni.pdf"]

    run = client.get(f"/api/ephemeral/runs/{run_id}").json()
    analyse = client.get(f"/api/ephemeral/analyses/{run['analyse_id']}").json()
    assert [lbl["name"] for lbl in analyse["classification"]["labels"]] == ["CNI", "RIB"]
    assert analyse["extraction"]["entities"] == []


def test_extraction_in_one_call(client: TestClient) -> None:
    created = client.post(
        "/api/ephemeral/extractions", files=FILE, data={"entities": ENTITIES, "extraction_prompt": "Extrait"}
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]

    body = client.get(f"/api/ephemeral/extractions/{run_id}").json()
    assert body["status"] == "en_cours"
    assert [d["name"] for d in body["documents"]] == ["cni.pdf"]

    run = client.get(f"/api/ephemeral/runs/{run_id}").json()
    analyse = client.get(f"/api/ephemeral/analyses/{run['analyse_id']}").json()
    assert [e["name"] for e in analyse["extraction"]["entities"]] == ["nom"]
    assert analyse["extraction"]["prompt"] == "Extrait"
    assert analyse["classification"]["labels"] == []


@pytest.mark.parametrize("labels", ["pas du json", "[]", '[{"definition": "sans nom"}]'])
def test_classification_rejects_invalid_labels(client: TestClient, labels: str) -> None:
    assert client.post("/api/ephemeral/classifications", files=FILE, data={"labels": labels}).status_code == 422


def test_extraction_rejects_unknown_entity_type(client: TestClient) -> None:
    bad = json.dumps([{"name": "nom", "type": "inconnu"}])
    assert client.post("/api/ephemeral/extractions", files=FILE, data={"entities": bad}).status_code == 422


def test_classification_ttl_hours_validation(client: TestClient) -> None:
    response = client.post(
        "/api/ephemeral/classifications", files=FILE, data={"labels": LABELS}, params={"ttl_hours": 0}
    )
    assert response.status_code == 400


def test_unknown_result_is_404(client: TestClient) -> None:
    unknown = uuid.uuid4()
    assert client.get(f"/api/ephemeral/classifications/{unknown}").status_code == 404
    assert client.get(f"/api/ephemeral/extractions/{unknown}").status_code == 404


def _prediction(kind: str, name: str, value: str, confidence: float, source: str = "textual") -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), kind=kind, name=name, value=value, confidence=confidence, source=source)


def _run(pages: list[SimpleNamespace], status: DossierStatus = DossierStatus.TERMINE) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        status=status,
        expires_at=datetime(2026, 10, 14),
        execution_steps=[],
        documents=[SimpleNamespace(name="dossier.pdf", pages=pages)],
    )


def test_classification_view_lists_labels_per_page_sorted_by_confidence() -> None:
    pages = [
        SimpleNamespace(
            page_number=2, predictions=[_prediction("label", "RIB", "RIB", 0.9), _prediction("entity", "x", "y", 1.0)]
        ),
        SimpleNamespace(
            page_number=1,
            predictions=[_prediction("label", "CNI", "CNI", 0.6), _prediction("label", "RIB", "RIB", 0.8)],
        ),
        SimpleNamespace(page_number=3, predictions=[]),
    ]
    out = to_classification_out(_run(pages))
    assert [p.page_number for p in out.documents[0].pages] == [1, 2, 3]
    assert [(label.name, label.confidence) for label in out.documents[0].pages[0].labels] == [
        ("RIB", 0.8),
        ("CNI", 0.6),
    ]
    assert [label.name for label in out.documents[0].pages[1].labels] == ["RIB"]  # l'entité est ignorée
    assert out.documents[0].pages[2].labels == []


def test_classification_view_exposes_the_source_with_textual_labels_first() -> None:
    pages = [
        SimpleNamespace(
            page_number=1,
            predictions=[
                _prediction("label", "RIB", "RIB", 0.99, source="visual"),
                _prediction("label", "CNI", "CNI", 0.5),
                _prediction("label", "CNI", "CNI", 0.7, source="visual"),
            ],
        )
    ]
    labels = to_classification_out(_run(pages)).documents[0].pages[0].labels
    assert [(label.name, label.source.value) for label in labels] == [
        ("CNI", "textual"),
        ("RIB", "visual"),
        ("CNI", "visual"),
    ]


def test_extraction_view_lists_entities_per_page_with_all_their_pages() -> None:
    name = _prediction("entity", "nom", "Dupont", 0.9)
    pages = [
        SimpleNamespace(page_number=1, predictions=[name, _prediction("label", "CNI", "CNI", 0.9)]),
        SimpleNamespace(page_number=2, predictions=[name]),
    ]
    out = to_extraction_out(_run(pages))
    first, second = out.documents[0].pages
    assert [(e.name, e.value, e.pages) for e in first.entities] == [("nom", "Dupont", [1, 2])]
    assert [(e.name, e.pages) for e in second.entities] == [("nom", [1, 2])]


def test_extraction_view_exposes_the_source_with_textual_entities_first() -> None:
    gliner = _prediction("entity", "nom", "Dupont", 0.95, source="gliner")
    llm = _prediction("entity", "nom", "Dupont", 0.8)
    pages = [SimpleNamespace(page_number=1, predictions=[gliner, llm])]
    entities = to_extraction_out(_run(pages)).documents[0].pages[0].entities
    assert [(e.name, e.source.value) for e in entities] == [("nom", "textual"), ("nom", "gliner")]


def test_failed_run_exposes_the_failed_step_message() -> None:
    run = _run([], status=DossierStatus.ECHEC)
    run.execution_steps = [SimpleNamespace(status="échec", output="LLM indisponible")]
    assert to_classification_out(run).error == "LLM indisponible"
    assert to_extraction_out(run).error == "LLM indisponible"


def test_api_key_is_accepted_as_a_bearer_token_and_scopes_like_x_app_token(client: TestClient) -> None:
    key_a = client.post("/api/app-tokens", json={"name": "bearer-a"}).json()["token"]
    key_b = client.post("/api/app-tokens", json={"name": "bearer-b"}).json()["token"]

    created = client.post(
        "/api/ephemeral/classifications", files=FILE, data={"labels": LABELS}, headers={"X-App-Token": key_a}
    )
    assert created.status_code == 201
    url = f"/api/ephemeral/classifications/{created.json()['run_id']}"

    assert client.get(url, headers={"Authorization": f"Bearer {key_a}"}).status_code == 200
    assert client.get(url, headers={"Authorization": f"Bearer {key_b}"}).status_code == 404
    # Un Bearer qui n'est pas une clé d'API (access token Keycloak) passe à la vérification Keycloak.
    assert client.get(url, headers={"Authorization": "Bearer un-access-token-keycloak"}).status_code == 404

    started = client.post(
        "/api/ephemeral/extractions",
        files=FILE,
        data={"entities": ENTITIES},
        headers={"Authorization": f"Bearer {key_a}"},
    )
    assert started.status_code == 201
    run_url = f"/api/ephemeral/extractions/{started.json()['run_id']}"
    assert client.get(run_url, headers={"X-App-Token": key_a}).status_code == 200  # même identité qu'en Bearer


def test_list_runs_shows_the_callers_runs_with_their_kind_and_persist(client: TestClient) -> None:
    classification = client.post("/api/ephemeral/classifications", files=FILE, data={"labels": LABELS}).json()["run_id"]
    extraction = client.post(
        "/api/ephemeral/extractions", files=FILE, data={"entities": ENTITIES, "persist": "true"}
    ).json()["run_id"]

    runs = {run["id"]: run for run in client.get("/api/ephemeral/runs").json()}

    assert runs[classification]["kind"] == "classification"
    assert runs[classification]["persist"] is False
    assert runs[extraction]["kind"] == "extraction"
    assert runs[extraction]["persist"] is True
    assert runs[extraction]["documents"] == ["cni.pdf"]
