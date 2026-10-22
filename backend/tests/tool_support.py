"""Aides partagées des tests des tools : faux client MCP, DNS public simulé, création d'un serveur."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.tool_servers import get_tool_lister
from app.services.tools.mcp_discovery import DiscoveredTool

LEGIFRANCE_TOOLS = [
    DiscoveredTool("rechercher_texte", "Recherche un texte de loi.", side_effect=False),
    DiscoveredTool("lire_article", "Renvoie un article.", side_effect=False),
    DiscoveredTool("envoyer_courriel", "Envoie un courriel.", side_effect=True),
]


class FakeLister:
    """Remplace le client MCP : aucun réseau."""

    def __init__(self, tools: list[DiscoveredTool] | Exception) -> None:
        self.tools = tools
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def list_tools(self, url: str, headers: dict[str, str], timeout: float) -> list[DiscoveredTool]:
        self.calls.append((url, headers))
        if isinstance(self.tools, Exception):
            raise self.tools
        return self.tools


@pytest.fixture
def lister() -> FakeLister:
    fake = FakeLister(LEGIFRANCE_TOOLS)
    app.dependency_overrides[get_tool_lister] = lambda: fake
    yield fake
    del app.dependency_overrides[get_tool_lister]


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tout nom se résout vers une adresse publique, sans interroger le DNS."""
    monkeypatch.setattr("app.services.tools.url_guard._system_resolver", lambda host: ["93.184.216.34"])


def create_server(
    client: TestClient, *, name: str | None = None, visibility: str = "private", tools: list[str] | None = None, **extra
) -> dict:
    body = {
        "name": name or f"Légifrance {uuid.uuid4().hex[:6]}",
        "url": "https://mcp.legifrance.example.gouv.fr/mcp",
        "auth_mode": "none",
        "visibility": visibility,
        "tool_names": tools or ["rechercher_texte", "lire_article"],
    } | extra
    response = client.post("/api/tool-servers", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def tool_id(server: dict, name: str) -> str:
    return next(tool["id"] for tool in server["tools"] if tool["name"] == name)
