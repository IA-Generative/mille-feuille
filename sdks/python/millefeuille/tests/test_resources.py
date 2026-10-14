from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

import httpx
import pytest
from conftest import NOW, analyse_json, dossier_json

from millefeuille import DossierStatus, WaitTimeoutError


def test_analyses_list_get_create_delete(make_client) -> None:
    aid = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/analyses":
            assert dict(request.url.params) == {"page": "2", "page_size": "5", "q": "cni"}
            item = {"id": aid, "name": "n", "description": "d", "created_at": NOW, "agent_count": 1}
            return httpx.Response(200, json={"items": [item], "total": 1, "page": 2, "page_size": 5, "pages": 1})
        if request.method == "POST":
            assert json.loads(request.content) == {"name": "n", "description": "d"}
            return httpx.Response(201, json=analyse_json(aid))
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json=analyse_json(aid))

    client, _ = make_client(handler)
    page = client.analyses.list(page=2, page_size=5, q="cni")
    assert page.total == 1 and page.items[0].agent_count == 1
    assert str(client.analyses.get(aid).id) == aid
    assert str(client.analyses.create("n", "d").id) == aid
    client.analyses.delete(aid)


def test_dossiers_flow(make_client, tmp_path: Path) -> None:
    did = str(uuid.uuid4())
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/api/dossiers" and request.method == "GET":
            return httpx.Response(
                200, json={"items": [dossier_json(did)], "total": 1, "page": 1, "page_size": 20, "pages": 1}
            )
        if request.url.path == "/api/dossiers" and request.method == "POST":
            body = json.loads(request.content)
            # Visibilité et groupes ne sont envoyés que s'ils sont donnés.
            assert body == {"name": "D", "analyse_id": None}
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.path.endswith("/documents"):
            body = request.content
            assert b'filename="cni.pdf"' in body and b"application/pdf" in body
            assert b'filename="document-2"' in body and b"raw" in body
            assert b'filename="named.txt"' in body
        return httpx.Response(200, json=dossier_json(did))

    client, _ = make_client(handler)
    pdf = tmp_path / "cni.pdf"
    pdf.write_bytes(b"%PDF")
    assert str(client.dossiers.list().items[0].id) == did
    client.dossiers.create("D")
    client.dossiers.get(did)
    client.dossiers.add_files(did, [pdf, b"raw", ("named.txt", io.BytesIO(b"hi"))])
    client.dossiers.launch(did)
    client.dossiers.stop(did)
    client.dossiers.delete(did)
    assert ("POST", f"/api/dossiers/{did}/launch") in calls
    assert ("POST", f"/api/dossiers/{did}/stop") in calls


def test_create_dossier_with_analyse(make_client) -> None:
    aid = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["analyse_id"] == str(aid)
        return httpx.Response(201, json=dossier_json())

    client, _ = make_client(handler)
    client.dossiers.create("D", analyse_id=aid)


def test_add_files_requires_files(make_client) -> None:
    client, _ = make_client(lambda r: httpx.Response(200, json=dossier_json()))
    with pytest.raises(ValueError):
        client.dossiers.add_files("x", [])


def test_file_like_object_uses_its_name(make_client, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert b'filename="f.bin"' in request.content
        return httpx.Response(200, json=dossier_json())

    client, _ = make_client(handler)
    path = tmp_path / "f.bin"
    path.write_bytes(b"x")
    with path.open("rb") as handle:
        client.dossiers.add_files("x", [handle])


def test_wait_polls_until_terminal(make_client, monkeypatch: pytest.MonkeyPatch) -> None:
    statuses = iter(["en_attente", "en_cours", "terminé"])
    client, seen = make_client(lambda r: httpx.Response(200, json=dossier_json(status=next(statuses))))
    monkeypatch.setattr("millefeuille._polling.time.sleep", lambda s: None)
    dossier = client.dossiers.wait("x", poll_interval=0)
    assert dossier.status is DossierStatus.TERMINE
    assert len(seen) == 3


def test_wait_timeout(make_client) -> None:
    client, _ = make_client(lambda r: httpx.Response(200, json=dossier_json(status="en_cours")))
    with pytest.raises(WaitTimeoutError) as info:
        client.dossiers.wait("x", timeout=0, poll_interval=1)
    assert isinstance(info.value, TimeoutError)


def test_tokens(make_client) -> None:
    tid = str(uuid.uuid4())
    token = {"id": tid, "name": "n", "created_by": "u", "created_at": NOW, "revoked_at": None, "last_used_at": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"items": [token], "total": 1, "page": 1, "page_size": 20, "pages": 1})
        if request.method == "POST":
            return httpx.Response(201, json={**token, "token": "ddd_secret"})
        return httpx.Response(204)

    client, _ = make_client(handler)
    assert client.tokens.list().items[0].name == "n"
    assert client.tokens.create("n").token == "ddd_secret"
    client.tokens.revoke(tid)


def test_status_terminal_flags() -> None:
    assert DossierStatus.ECHEC.is_terminal and DossierStatus.ARRETE.is_terminal
    assert not DossierStatus.EN_COURS.is_terminal


def test_create_dossier_with_access(make_client) -> None:
    client, seen = make_client(lambda request: httpx.Response(201, json=dossier_json(str(uuid.uuid4()))))

    client.dossiers.create("D", visibility="restricted", group_paths=["/equipe-a"])

    assert json.loads(seen[0].content) == {
        "name": "D",
        "analyse_id": None,
        "visibility": "restricted",
        "group_paths": ["/equipe-a"],
    }
