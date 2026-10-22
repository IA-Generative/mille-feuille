from types import SimpleNamespace

from app.services.tools.mcp_discovery import to_discovered_tool


def mcp_tool(*, read_only: bool | None, description: str | None = "Cherche.") -> SimpleNamespace:
    annotations = None if read_only is None else SimpleNamespace(read_only_hint=read_only)
    return SimpleNamespace(
        name="chercher", description=description, input_schema={"type": "object"}, annotations=annotations
    )


def test_a_read_only_tool_does_not_ask_for_confirmation() -> None:
    assert to_discovered_tool(mcp_tool(read_only=True)).side_effect is False


def test_a_tool_without_the_read_only_hint_is_assumed_to_modify_data() -> None:
    assert to_discovered_tool(mcp_tool(read_only=None)).side_effect is True
    assert to_discovered_tool(mcp_tool(read_only=False)).side_effect is True


def test_a_missing_description_becomes_an_empty_string() -> None:
    assert to_discovered_tool(mcp_tool(read_only=True, description=None)).description == ""


def test_the_real_client_lists_the_tools_of_a_real_mcp_server(client) -> None:
    """Le vrai client MCP contre le serveur MCP de la plateforme, en mémoire : handshake, session, `tools/list`."""
    import httpx2

    from app.main import app
    from app.services.tools.mcp_discovery import McpToolLister

    token = client.post("/api/app-tokens", json={"name": "discovery-test"}).json()["token"]
    lister = McpToolLister(transport=httpx2.ASGITransport(app=app))

    async def run():
        return await lister.list_tools("http://testserver/mcp", {"Authorization": f"Bearer {token}"}, 10.0)

    # Dans la boucle du TestClient : le pool de connexions de l'application y est lié (comme tests/test_mcp.py).
    tools = client.portal.call(run)

    names = {tool.name for tool in tools}
    assert "create_ephemeral_analysis" in names
    assert all(tool.input_schema.get("type") == "object" for tool in tools)
