import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.tool_servers import get_identity_tokens, get_tool_lister
from app.services.tools.mcp_discovery import DiscoveredTool, DiscoveryError
from tests.access_support import As

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


def create(client: TestClient, *, name: str | None = None, visibility: str = "private", tools=None, **extra) -> dict:
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


def ids(client: TestClient, q: str) -> set[str]:
    return {server["id"] for server in client.get("/api/tool-servers", params={"q": q}).json()["items"]}


def test_internal_tools_are_listed(client: TestClient) -> None:
    tools = client.get("/api/tools/internal").json()
    assert {t["id"] for t in tools} >= {"base_connaissances", "notes_internes"}
    assert all(t["kind"] == "internal" for t in tools)


def test_discover_lists_the_tools_without_saving(client: TestClient, lister: FakeLister) -> None:
    response = client.post(
        "/api/tool-servers/discover", json={"url": "https://mcp.example.gouv.fr/mcp", "auth_mode": "none"}
    )
    assert response.status_code == 200
    assert [t["name"] for t in response.json()["tools"]] == ["rechercher_texte", "lire_article", "envoyer_courriel"]
    assert response.json()["tools"][2]["side_effect"] is True
    assert lister.calls[0][1] == {}  # aucune authentification


def test_static_token_is_refused_for_now(client: TestClient, lister: FakeLister) -> None:
    response = client.post(
        "/api/tool-servers/discover", json={"url": "https://mcp.example.gouv.fr/mcp", "auth_mode": "static_token"}
    )
    assert response.status_code == 422
    assert "jeton statique" in response.text.lower()


class FakeIdentityTokens:
    """Remplace session + échange Keycloak : aucune connexion à Keycloak ni à Redis."""

    def __init__(self) -> None:
        self.calls: list[tuple[str | None, str | None]] = []

    async def token_for(self, user_id: str | None, audience: str | None) -> str:
        self.calls.append((user_id, audience))
        return f"exchanged-for-{audience}"


@pytest.fixture
def identity_tokens() -> FakeIdentityTokens:
    fake = FakeIdentityTokens()
    app.dependency_overrides[get_identity_tokens] = lambda: fake
    yield fake
    del app.dependency_overrides[get_identity_tokens]


def test_token_exchange_sends_the_exchanged_token_for_the_servers_audience(
    client: TestClient, lister: FakeLister, identity_tokens: FakeIdentityTokens
) -> None:
    body = {"url": "https://mcp.example.gouv.fr/mcp", "auth_mode": "token_exchange", "audience": "mcp-legifrance"}
    response = client.post("/api/tool-servers/discover", json=body)

    assert response.status_code == 200
    assert lister.calls[0][1] == {"Authorization": "Bearer exchanged-for-mcp-legifrance"}
    assert identity_tokens.calls == [("dev-user", "mcp-legifrance")]


def test_token_exchange_requires_an_audience(client: TestClient, lister: FakeLister) -> None:
    response = client.post(
        "/api/tool-servers/discover", json={"url": "https://mcp.example.gouv.fr/mcp", "auth_mode": "token_exchange"}
    )
    assert response.status_code == 422
    assert "audience" in response.text.lower()
    assert lister.calls == []


def test_token_exchange_without_a_session_says_so_with_a_stable_code(client: TestClient, lister: FakeLister) -> None:
    """Sans simulation : la personne des tests n'a pas de session Keycloak."""
    body = {"url": "https://mcp.example.gouv.fr/mcp", "auth_mode": "token_exchange", "audience": "mcp-legifrance"}
    response = client.post("/api/tool-servers/discover", json=body)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "session_requise"
    assert lister.calls == []


def test_a_token_exchange_server_keeps_its_audience_and_reuses_it_on_refresh(
    client: TestClient, lister: FakeLister, identity_tokens: FakeIdentityTokens
) -> None:
    server = create(client, auth_mode="token_exchange", audience="mcp-legifrance")
    assert server["audience"] == "mcp-legifrance"

    client.post(f"/api/tool-servers/{server['id']}/refresh")

    assert [audience for _, audience in identity_tokens.calls] == ["mcp-legifrance", "mcp-legifrance"]


@pytest.mark.parametrize(
    "url", ["http://mcp.example.gouv.fr/mcp", "https://user:pw@mcp.example.gouv.fr/mcp", "n'importe quoi"]
)
def test_unsafe_urls_are_refused_before_any_connection(client: TestClient, lister: FakeLister, url: str) -> None:
    response = client.post("/api/tool-servers/discover", json={"url": url, "auth_mode": "none"})
    assert response.status_code == 422
    assert lister.calls == []


def test_a_host_resolving_to_a_private_address_is_refused(
    client: TestClient, lister: FakeLister, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.tools.url_guard._system_resolver", lambda host: ["169.254.169.254"])
    response = client.post(
        "/api/tool-servers/discover", json={"url": "https://metadata.example.org/mcp", "auth_mode": "none"}
    )
    assert response.status_code == 422
    assert lister.calls == []


def test_a_server_that_is_not_mcp_gives_a_bad_gateway(client: TestClient, lister: FakeLister) -> None:
    lister.tools = DiscoveryError("Le serveur ne répond pas comme un serveur MCP.")
    response = client.post(
        "/api/tool-servers/discover", json={"url": "https://mcp.example.gouv.fr/mcp", "auth_mode": "none"}
    )
    assert response.status_code == 502


def test_create_keeps_every_tool_but_authorizes_only_the_chosen_ones(client: TestClient, lister: FakeLister) -> None:
    server = create(client, tools=["rechercher_texte"])
    assert server["owned_by_me"] is True
    assert server["visibility"] == "private"
    enabled = {t["name"]: t["enabled"] for t in server["tools"]}
    assert enabled == {"rechercher_texte": True, "lire_article": False, "envoyer_courriel": False}
    assert {t["name"]: t["side_effect"] for t in server["tools"]}["envoyer_courriel"] is True


def test_create_rejects_a_tool_the_server_does_not_expose(client: TestClient, lister: FakeLister) -> None:
    response = client.post(
        "/api/tool-servers",
        json={"name": "X", "url": "https://mcp.example.gouv.fr/mcp", "auth_mode": "none", "tool_names": ["fantome"]},
    )
    assert response.status_code == 422
    assert "fantome" in response.text


def test_create_requires_at_least_one_tool(client: TestClient, lister: FakeLister) -> None:
    response = client.post(
        "/api/tool-servers",
        json={"name": "X", "url": "https://mcp.example.gouv.fr/mcp", "auth_mode": "none", "tool_names": []},
    )
    assert response.status_code == 422


def test_list_is_paginated_and_searchable(client: TestClient, lister: FakeLister) -> None:
    marker = uuid.uuid4().hex[:8]
    for i in range(3):
        create(client, name=f"Annuaire {marker} {i}")
    page = client.get("/api/tool-servers", params={"q": marker, "page_size": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 2 and page["pages"] == 2
    assert client.get("/api/tool-servers", params={"q": "ACCENT-INCONNU-" + marker}).json()["total"] == 0


def test_visibility_private_groups_and_all(client: TestClient, lister: FakeLister, world: dict) -> None:
    marker = uuid.uuid4().hex[:8]
    with As(world["alice"]):  # groupe a
        private = create(client, name=f"Privé {marker}", visibility="private")["id"]
        in_groups = create(client, name=f"Groupes {marker}", visibility="groups")["id"]
        public = create(client, name=f"Tous {marker}", visibility="all")["id"]
    with As(world["carol"]):  # groupes a et b
        assert ids(client, marker) == {in_groups, public}
    with As(world["bob"]):  # groupe b seulement
        assert ids(client, marker) == {public}
        assert client.get(f"/api/tool-servers/{private}").status_code == 404
        assert client.get(f"/api/tool-servers/{in_groups}").status_code == 404
    with As(world["root"]):  # administrateur
        assert ids(client, marker) == {private, in_groups, public}


def test_only_the_owner_or_an_admin_can_delete_or_refresh(client: TestClient, lister: FakeLister, world: dict) -> None:
    with As(world["alice"]):
        server_id = create(client, visibility="all")["id"]
    with As(world["bob"]):
        assert client.delete(f"/api/tool-servers/{server_id}").status_code == 403
        assert client.post(f"/api/tool-servers/{server_id}/refresh").status_code == 403
    with As(world["alice"]):
        assert client.delete(f"/api/tool-servers/{server_id}").status_code == 204
        assert client.get(f"/api/tool-servers/{server_id}").status_code == 404


def test_an_invisible_server_cannot_be_deleted_by_someone_else(
    client: TestClient, lister: FakeLister, world: dict
) -> None:
    with As(world["alice"]):
        server_id = create(client, visibility="private")["id"]
    with As(world["bob"]):
        assert client.delete(f"/api/tool-servers/{server_id}").status_code == 404


def test_refresh_keeps_authorizations_adds_new_tools_disabled_and_drops_gone_ones(
    client: TestClient, lister: FakeLister
) -> None:
    server = create(client, tools=["rechercher_texte"])
    lister.tools = [
        DiscoveredTool("rechercher_texte", "Description mise à jour.", side_effect=False),
        DiscoveredTool("nouveau_tool", "Un nouveau tool.", side_effect=False),
    ]
    refreshed = client.post(f"/api/tool-servers/{server['id']}/refresh").json()
    tools = {t["name"]: t for t in refreshed["tools"]}
    assert set(tools) == {"rechercher_texte", "nouveau_tool"}  # lire_article et envoyer_courriel ont disparu
    assert tools["rechercher_texte"]["enabled"] is True
    assert tools["rechercher_texte"]["description"] == "Description mise à jour."
    assert tools["nouveau_tool"]["enabled"] is False
