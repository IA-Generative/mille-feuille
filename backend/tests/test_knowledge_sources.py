import asyncio
import uuid

import httpx2
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.knowledge_sources import get_source_probe
from app.services.knowledge.client import HttpKnowledgeClient
from app.services.knowledge.connection import HttpSourceProbe, ProbeError
from tests.access_support import As
from tests.tool_support import FakeIdentityTokens


class FakeProbe:
    """Remplace le client du fournisseur : aucun réseau."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def probe(self, url: str, headers: dict[str, str], timeout: float) -> None:
        self.calls.append((url, headers))
        if self.error:
            raise self.error


@pytest.fixture
def probe() -> FakeProbe:
    fake = FakeProbe()
    app.dependency_overrides[get_source_probe] = lambda: fake
    yield fake
    del app.dependency_overrides[get_source_probe]


def add(client: TestClient, *, visibility: str = "private", **extra):
    body = {
        "name": f"Références {uuid.uuid4().hex[:6]}",
        "url": "https://kb.example.gouv.fr",
        "auth_mode": "none",
        "visibility": visibility,
    } | extra
    return client.post("/api/knowledge-sources", json=body)


def test_a_source_is_added_after_its_connection_is_checked(client: TestClient, probe: FakeProbe) -> None:
    response = add(client, name="  Guide des subventions ")

    assert response.status_code == 201, response.text
    source = response.json()
    assert source["name"] == "Guide des subventions" and source["owned_by_me"] is True
    assert source["visibility"] == "private" and "credentials" not in source
    assert probe.calls == [("https://kb.example.gouv.fr", {})]
    assert client.get(f"/api/knowledge-sources/{source['id']}").json()["id"] == source["id"]


def test_the_exchanged_token_for_the_audience_is_what_the_provider_receives(
    client: TestClient, probe: FakeProbe, identity_tokens: FakeIdentityTokens
) -> None:
    response = add(client, auth_mode="token_exchange", audience="kb-subventions")

    assert response.status_code == 201
    assert probe.calls[0][1] == {"Authorization": "Bearer exchanged-for-kb-subventions"}
    assert identity_tokens.calls == [("dev-user", "kb-subventions")]


def test_identity_needs_an_audience_and_a_static_token_is_refused_for_now(client: TestClient, probe: FakeProbe) -> None:
    assert add(client, auth_mode="token_exchange").status_code == 422
    refused = add(client, auth_mode="static_token")
    assert refused.status_code == 422 and "jeton statique" in refused.text.lower()
    assert add(client, name="   ").status_code == 422
    assert probe.calls == []


@pytest.mark.parametrize("url", ["http://kb.example.gouv.fr", "https://user:pw@kb.example.gouv.fr", "ftp://x"])
def test_the_same_url_guard_as_mcp_servers_applies(client: TestClient, probe: FakeProbe, url: str) -> None:
    assert add(client, url=url).status_code == 422
    assert probe.calls == []


def test_a_provider_that_is_not_to_the_contract_is_not_added(client: TestClient) -> None:
    app.dependency_overrides[get_source_probe] = lambda: FakeProbe(ProbeError("Le fournisseur ne répond pas."))
    try:
        response = add(client, name="Introuvable-" + uuid.uuid4().hex[:6])
    finally:
        del app.dependency_overrides[get_source_probe]

    assert response.status_code == 502 and "ne répond pas" in response.json()["detail"]
    assert client.get("/api/knowledge-sources", params={"q": "Introuvable-"}).json()["total"] == 0


def test_visibility_is_the_one_of_mcp_servers(client: TestClient, probe: FakeProbe, world: dict) -> None:
    with As(world["alice"]):  # groupe a
        private = add(client).json()["id"]
        groups = add(client, visibility="groups").json()["id"]
        everyone = add(client, visibility="all").json()["id"]

    def seen(person: str) -> set[str]:
        with As(world[person]):
            items = client.get("/api/knowledge-sources", params={"page_size": 100}).json()["items"]
            return {s["id"] for s in items} & {private, groups, everyone}

    assert seen("alice") == {private, groups, everyone}
    assert seen("carol") == {groups, everyone}  # groupes a et b
    assert seen("bob") == {everyone}  # groupe b seulement
    assert seen("root") == {private, groups, everyone}  # administrateur
    with As(world["bob"]):
        assert client.get(f"/api/knowledge-sources/{private}").status_code == 404  # comme si elle n'existait pas
        assert client.delete(f"/api/knowledge-sources/{everyone}").status_code == 403  # vue, pas à lui


def test_the_list_is_paginated_and_searchable(client: TestClient, probe: FakeProbe) -> None:
    tag = uuid.uuid4().hex[:8]
    for number in range(3):
        assert add(client, name=f"Base {tag} {number}").status_code == 201

    page = client.get("/api/knowledge-sources", params={"q": tag, "page_size": 2}).json()

    assert (page["total"], len(page["items"]), page["pages"]) == (3, 2, 2)


def test_only_the_owner_or_an_administrator_deletes_a_source(client: TestClient, probe: FakeProbe, world: dict) -> None:
    with As(world["alice"]):
        source = add(client, visibility="all").json()["id"]
    with As(world["bob"]):
        assert client.delete(f"/api/knowledge-sources/{source}").status_code == 403
    with As(world["root"]):
        assert client.delete(f"/api/knowledge-sources/{source}").status_code == 204
        assert client.get(f"/api/knowledge-sources/{source}").status_code == 404


def test_a_source_can_be_checked_again_with_the_identity_of_the_caller(
    client: TestClient, probe: FakeProbe, identity_tokens: FakeIdentityTokens
) -> None:
    source = add(client, auth_mode="token_exchange", audience="kb-subventions").json()["id"]

    assert client.post(f"/api/knowledge-sources/{source}/check").status_code == 204
    assert len(probe.calls) == 2


# --- Le client réel, contre un faux fournisseur en mémoire ---


def run_probe(handler) -> None:
    probe = HttpSourceProbe(HttpKnowledgeClient(transport=httpx2.MockTransport(handler)))
    asyncio.run(probe.probe("https://kb.example.gouv.fr/", {"Authorization": "Bearer t"}, 5))


def test_the_real_probe_calls_the_collections_route_of_the_contract() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"items": [], "total": 0, "page": 1, "page_size": 1})

    run_probe(handler)

    assert str(seen[0].url) == "https://kb.example.gouv.fr/v1/collections?page=1&page_size=1"
    assert seen[0].headers["Authorization"] == "Bearer t"


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx2.Response(401), "refusé l'authentification"),
        (httpx2.Response(403), "pas accès"),
        (httpx2.Response(500), "ne répond pas"),
        (httpx2.Response(200, text="<html>"), "pas du JSON"),
        (httpx2.Response(200, json={"collections": []}), "contrat"),
    ],
)
def test_the_real_probe_reports_a_provider_that_is_not_to_the_contract(response, message) -> None:
    with pytest.raises(ProbeError, match=message):
        run_probe(lambda request: response)


def test_the_real_probe_reports_an_unreachable_provider() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refusé")

    with pytest.raises(ProbeError, match="ne répond pas"):
        run_probe(handler)
