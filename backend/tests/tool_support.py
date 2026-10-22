"""Aides partagées des tests des tools : faux client MCP, DNS public simulé, création d'un serveur."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.internal_tools import get_tool_caller
from app.routers.tool_servers import get_identity_tokens, get_tool_lister
from app.services.tools.credentials_errors import CredentialsUnavailableError
from app.services.tools.mcp_caller import RawToolResult
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


class FakeIdentityTokens:
    """Remplace session + échange Keycloak : aucune connexion à Keycloak ni à Redis."""

    def __init__(self) -> None:
        self.calls: list[tuple[str | None, str | None]] = []

    async def token_for(self, user_id: str | None, audience: str | None) -> str:
        self.calls.append((user_id, audience))
        if not user_id:
            raise CredentialsUnavailableError("identite_absente", "Aucune personne n'est associée à cet appel.")
        return f"exchanged-for-{audience}"


@pytest.fixture
def identity_tokens() -> FakeIdentityTokens:
    fake = FakeIdentityTokens()
    app.dependency_overrides[get_identity_tokens] = lambda: fake
    yield fake
    del app.dependency_overrides[get_identity_tokens]


class FakeCaller:
    """Remplace le client MCP : aucun réseau."""

    def __init__(self, result: RawToolResult | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, str], str, dict[str, Any]]] = []

    async def call_tool(self, url, headers, name, arguments, timeout) -> RawToolResult:
        self.calls.append((url, headers, name, arguments))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def caller() -> FakeCaller:
    fake = FakeCaller(RawToolResult(text="Article L1111-1 : …", is_error=False))
    app.dependency_overrides[get_tool_caller] = lambda: fake
    yield fake
    del app.dependency_overrides[get_tool_caller]


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
