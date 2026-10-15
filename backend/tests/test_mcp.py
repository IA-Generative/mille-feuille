import base64
import json

import httpx2
import pytest
from fastapi.testclient import TestClient
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.main import app


@pytest.fixture(autouse=True)
def _no_real_celery_dispatch_for_mcp_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("dispatch_dossier_pipeline",):
        monkeypatch.setattr(f"app.routers.ephemeral.{name}", lambda *args, **kwargs: None)


def _mcp_session(token: str):
    """Un vrai client MCP (SDK officiel), pas un appel direct aux tools :
    exerce le protocole complet (handshake, session Streamable HTTP,
    JSON-RPC) plutôt que de contourner la couche transport."""
    transport = httpx2.ASGITransport(app=app)
    http_client = httpx2.AsyncClient(
        transport=transport, base_url="http://testserver", headers={"Authorization": f"Bearer {token}"}
    )
    return streamable_http_client(url="http://testserver/mcp", http_client=http_client)


def _call_tool_json(result) -> dict:
    assert not result.is_error, result.content
    return json.loads(result.content[0].text)


def test_mcp_full_cycle(client: TestClient) -> None:
    token = client.post("/api/app-tokens", json={"name": "mcp-test"}).json()["token"]

    async def run() -> None:
        async with _mcp_session(token) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                assert init.server_info.name == "mille-feuille-ephemeral"

                tools = await session.list_tools()
                assert {t.name for t in tools.tools} == {
                    "create_ephemeral_analysis",
                    "get_ephemeral_analysis",
                    "delete_ephemeral_analysis",
                    "run_ephemeral_analysis",
                    "get_ephemeral_run",
                    "stop_ephemeral_run",
                    "delete_ephemeral_run",
                }

                created = _call_tool_json(
                    await session.call_tool(
                        "create_ephemeral_analysis",
                        {
                            "name": "Analyse MCP",
                            "classification_prompt": "Classe le document",
                            "labels": [{"name": "CNI", "definition": "Carte d'identité"}],
                        },
                    )
                )
                analyse_id = created["analyse_id"]

                fetched = _call_tool_json(await session.call_tool("get_ephemeral_analysis", {"analyse_id": analyse_id}))
                assert fetched["classification"]["prompt"] == "Classe le document"

                run_created = _call_tool_json(
                    await session.call_tool(
                        "run_ephemeral_analysis",
                        {
                            "analyse_id": analyse_id,
                            "files": [
                                {
                                    "name": "cni.pdf",
                                    "content_base64": base64.b64encode(b"fake-bytes").decode(),
                                    "mimetype": "application/pdf",
                                }
                            ],
                            "ttl_hours": 48,
                        },
                    )
                )
                run_id = run_created["run_id"]

                status = _call_tool_json(await session.call_tool("get_ephemeral_run", {"run_id": run_id}))
                assert status["status"] == "en_cours"
                assert status["expires_at"] is None

                stopped = _call_tool_json(await session.call_tool("stop_ephemeral_run", {"run_id": run_id}))
                assert stopped["status"] == "arrêté"
                assert stopped["expires_at"] is not None

                deleted_run = _call_tool_json(await session.call_tool("delete_ephemeral_run", {"run_id": run_id}))
                assert deleted_run == {"deleted": True}

                # L'analyse persist=false a déjà été supprimée à l'arrêt du run (seul son résultat était
                # conservé, et vient d'être supprimé par delete_ephemeral_run).
                deleted_analyse = _call_tool_json(
                    await session.call_tool("delete_ephemeral_analysis", {"analyse_id": analyse_id})
                )
                assert deleted_analyse == {"error": "Analyse éphémère introuvable", "status_code": 404}

                gone = _call_tool_json(await session.call_tool("get_ephemeral_run", {"run_id": run_id}))
                assert gone == {"error": "Run éphémère introuvable", "status_code": 404}

    client.portal.call(run)


def test_mcp_requires_bearer_token(client: TestClient) -> None:
    transport = httpx2.ASGITransport(app=app)

    async def run() -> None:
        http_client = httpx2.AsyncClient(transport=transport, base_url="http://testserver")
        response = await http_client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert response.status_code == 401

    client.portal.call(run)


def test_mcp_rejects_invalid_token(client: TestClient) -> None:
    transport = httpx2.ASGITransport(app=app)

    async def run() -> None:
        http_client = httpx2.AsyncClient(
            transport=transport, base_url="http://testserver", headers={"Authorization": "Bearer not-a-real-token"}
        )
        response = await http_client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert response.status_code == 401

    client.portal.call(run)
