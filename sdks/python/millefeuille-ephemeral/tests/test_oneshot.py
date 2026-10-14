"""Classification et extraction en un appel, liste des runs et version du backend."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from conftest import classification_json, extraction_json
from contract import example
from pydantic import ValidationError

from millefeuille_ephemeral import TTLValidationError

LABELS = [{"name": "CNI", "definition": "Carte d'identité"}, {"name": "RIB", "definition": "Relevé"}]
ENTITIES = [{"name": "nom", "definition": "Nom de famille", "type": "texte"}]


def test_classifications_create_sends_one_file_and_json_labels(make_client) -> None:
    rid = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path == "/api/ephemeral/classifications"
            assert request.url.params["ttl_hours"] == "48"
            assert b'name="file"; filename="cni.pdf"' in request.content
            assert b'name="multi_label"\r\n\r\ntrue' in request.content
            assert b'name="persist"\r\n\r\nfalse' in request.content
            assert b'name="classification_prompt"\r\n\r\nClasse.' in request.content
            return httpx.Response(201, json={"run_id": rid})
        assert request.url.path == f"/api/ephemeral/classifications/{rid}"
        return httpx.Response(200, json=classification_json(rid, status="en_cours"))

    client, seen = make_client(handler)
    result = client.classifications.create(
        ("cni.pdf", b"%PDF"), LABELS, multi_label=True, prompt="Classe.", ttl_hours=48
    )

    assert str(result.run_id) == rid and result.status.value == "en_cours"
    body = seen[0].content.decode()
    labels_part = body.split('name="labels"\r\n\r\n')[1].split("\r\n")[0]
    assert json.loads(labels_part) == LABELS
    page = result.documents[0].pages[0]
    assert page.labels[0].source.value in {"textual", "visual"}


def test_classifications_validate_before_any_request(make_client) -> None:
    client, seen = make_client(lambda request: httpx.Response(500))

    with pytest.raises(ValueError, match="catégorie"):
        client.classifications.create(b"x", [])
    with pytest.raises(ValidationError):
        client.classifications.create(b"x", [{"definition": "sans nom"}])
    with pytest.raises(TTLValidationError):
        client.classifications.create(b"x", LABELS, ttl_hours=0)

    assert seen == []


def test_extractions_create_sends_one_file_and_json_entities(make_client) -> None:
    rid = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path == "/api/ephemeral/extractions"
            assert (
                b'name="file"; filename="doc-1"' in request.content
                or b'name="file"; filename="document-1"' in request.content
            )
            assert b'name="extraction_prompt"\r\n\r\nExtrais.' in request.content
            assert b'name="persist"\r\n\r\ntrue' in request.content
            return httpx.Response(201, json={"run_id": rid})
        return httpx.Response(200, json=extraction_json(rid))

    client, seen = make_client(handler)
    result = client.extractions.create(b"x", ENTITIES, prompt="Extrais.", persist=True)

    entity = result.documents[0].pages[0].entities[0]
    assert entity.source.value in {"textual", "gliner"} and isinstance(entity.pages, list)
    body = seen[0].content.decode()
    entities_part = body.split('name="entities"\r\n\r\n')[1].split("\r\n")[0]
    assert json.loads(entities_part) == ENTITIES


def test_extractions_validate_before_any_request(make_client) -> None:
    client, seen = make_client(lambda request: httpx.Response(500))

    with pytest.raises(ValueError, match="entité"):
        client.extractions.create(b"x", [])
    with pytest.raises(ValidationError):
        client.extractions.create(b"x", [{"name": "n", "definition": "d", "type": "inconnu"}])

    assert seen == []


def test_classify_waits_for_the_result_and_cleans_up(make_client, monkeypatch: pytest.MonkeyPatch) -> None:
    rid = str(uuid.uuid4())
    statuses = iter(["en_cours", "en_cours", "terminé"])
    log: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        log.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(201, json={"run_id": rid})
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json=classification_json(rid, status=next(statuses)))

    monkeypatch.setattr("millefeuille._polling.time.sleep", lambda s: None)
    client, _ = make_client(handler)

    result = client.classify(b"x", LABELS, timeout=10, poll_interval=0, cleanup=True)

    assert result.status.is_terminal
    assert log[-1] == ("DELETE", f"/api/ephemeral/runs/{rid}")


def test_extract_without_cleanup_keeps_the_run(make_client, monkeypatch: pytest.MonkeyPatch) -> None:
    rid = str(uuid.uuid4())
    log: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        log.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(201, json={"run_id": rid})
        return httpx.Response(200, json=extraction_json(rid))

    monkeypatch.setattr("millefeuille._polling.time.sleep", lambda s: None)
    client, _ = make_client(handler)

    result = client.extract(b"x", ENTITIES, poll_interval=0)

    assert result.status.is_terminal
    assert not any(method == "DELETE" for method, _ in log)


def test_classifications_wait_timeout(make_client) -> None:
    from millefeuille_ephemeral import WaitTimeoutError

    client, _ = make_client(lambda request: httpx.Response(200, json=classification_json(status="en_cours")))
    with pytest.raises(WaitTimeoutError):
        client.classifications.wait("r", timeout=0, poll_interval=1)


def test_runs_list_returns_summaries(make_client) -> None:
    items = [
        example("EphemeralRunSummary", kind="classification", persist=False, ended_at=None, expires_at=None),
        example("EphemeralRunSummary", kind="analyse", persist=True, ended_at=None, expires_at=None),
    ]
    client, seen = make_client(lambda request: httpx.Response(200, json=items))

    runs = client.runs.list()

    assert seen[0].url.path == "/api/ephemeral/runs"
    assert [run.kind for run in runs] == ["classification", "analyse"]
    assert runs[1].persist is True


def test_version_reads_the_backend_version(make_client) -> None:
    client, seen = make_client(lambda request: httpx.Response(200, json={"version": "0.22.0"}))

    assert client.version() == "0.22.0"
    assert seen[0].url.path == "/api/version"
