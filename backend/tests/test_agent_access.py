"""L'agent assistant agit au nom d'une personne (issue #222) : il ne voit jamais plus de dossiers qu'elle.

Deux chemins : l'agent de l'interface (le backend agit pour la personne qui a ouvert la conversation) et le serveur
MCP (le jeton d'application a un propriétaire dont l'agent a les droits)."""

import json
import uuid

import httpx2
import pytest
from fastapi.testclient import TestClient
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.agent.helper.tools import HelperTools
from app.main import app
from app.mcp.helper_server import mcp_server
from tests.access_support import As
from tests.test_dossier_access import _create, _events

# --- L'agent de l'interface (la fenêtre de l'assistant) ---


def _agent(client: TestClient, person_id: str, work):  # noqa: ANN001, ANN202
    """Exécute `work(outils)` sur la boucle de l'application, les outils de l'assistant agissant pour cette personne."""

    async def run_work():  # noqa: ANN202
        return await work(HelperTools(person_id))

    return client.portal.call(run_work)


def _id_of(answer: str) -> str:
    return answer.split("(id: ")[1].split(")")[0]


def test_the_agent_lists_only_what_the_person_sees(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        restricted = _create(client, analyse)
        open_one = _create(client, analyse, visibility="analyse")

    def listed(person) -> str:  # noqa: ANN001
        async def every_page(tools: HelperTools) -> str:
            return "\n".join([await tools.list_dossiers(page=page, page_size=100) for page in range(1, 6)])

        return _agent(client, person.user_id, every_page)

    for dossier in (restricted, open_one):
        assert dossier["id"] in listed(world["alice"])
    assert restricted["id"] not in listed(world["bob"]) and open_one["id"] in listed(world["bob"])


def test_without_an_acting_person_the_agent_sees_no_restricted_dossier(
    client: TestClient, analyse: dict, world: dict
) -> None:
    with As(world["alice"]):
        restricted = _create(client, analyse)

    anonymous = _agent(client, "", lambda tools: tools.get_dossier(restricted["id"]))

    assert anonymous == "Erreur : Dossier introuvable"


@pytest.mark.parametrize("tool", ["get_dossier", "run_dossier"])
def test_the_agent_cannot_reach_a_dossier_the_person_cannot_see(
    client: TestClient, analyse: dict, world: dict, tool: str
) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)  # /a

    outsider = _agent(client, world["bob"].user_id, lambda tools: getattr(tools, tool)(dossier["id"]))
    member = _agent(client, world["carol"].user_id, lambda tools: getattr(tools, tool)(dossier["id"]))

    assert outsider == "Erreur : Dossier introuvable"
    assert member != "Erreur : Dossier introuvable"


def test_the_agent_creates_dossiers_restricted_to_the_persons_groups(
    client: TestClient, analyse: dict, world: dict
) -> None:
    created = _agent(
        client, world["alice"].user_id, lambda tools: tools.create_dossier("Créé par l'agent", analyse["id"])
    )

    assert created.startswith("Dossier « Créé par l'agent » créé"), created
    with As(world["alice"]):
        groups = client.get(f"/api/dossiers/{_id_of(created)}/access").json()
    assert groups["visibility"] == "restricted" and [g["path"] for g in groups["groups"]] == [world["a"]]


def test_a_person_without_groups_cannot_have_the_agent_create_a_dossier(client: TestClient, analyse: dict) -> None:
    created = _agent(client, "inconnu", lambda tools: tools.create_dossier("Sans groupe", analyse["id"]))

    assert created.startswith("Erreur :") and "groups_required" in created


def test_an_administrator_entering_through_the_agent_is_traced(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["bob"]):
        dossier = _create(client, analyse)  # /b : root n'en fait pas partie

    answer = _agent(client, world["root"].user_id, lambda tools: tools.get_dossier(dossier["id"]))

    assert answer.startswith("Dossier « ") and not answer.startswith("Erreur")
    with As(world["root"]):
        (event,) = _events(client, dossier["id"], "admin_access")
    assert event["actor_id"] == world["root"].user_id


# --- Serveur MCP ---


def _mcp(token: str):
    http_client = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )
    return streamable_http_client(url="http://testserver/mcp/helper/", http_client=http_client)


def _json(result) -> dict:
    assert not result.is_error, result.content
    return json.loads(result.content[0].text)


def _token_of(client: TestClient, person) -> str:
    with As(person):
        return client.post("/api/app-tokens", json={"name": f"agent-{uuid.uuid4().hex[:6]}"}).json()["token"]


async def _call(token: str, tool: str, arguments: dict | None = None) -> dict:
    async with _mcp(token) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return _json(await session.call_tool(tool, arguments or {}))


def test_every_mcp_tool_that_takes_a_dossier_is_known_and_guarded(client: TestClient) -> None:
    """Garde-fou : un outil MCP ajouté qui prend un identifiant de dossier fait échouer ce test, jusqu'à ce qu'il soit
    filtré par les droits de la personne et ajouté ci-dessous (et au test d'invisibilité)."""

    async def tools() -> list:
        return await mcp_server.list_tools()

    with_dossier = {t.name for t in client.portal.call(tools) if "dossier_id" in t.input_schema.get("properties", {})}

    assert with_dossier == {"add_dossier_files", "get_dossier", "run_dossier", "get_dossier_results"}


@pytest.mark.parametrize(
    ("tool", "extra"),
    [
        ("get_dossier", {}),
        ("get_dossier_results", {}),
        ("run_dossier", {}),
        ("add_dossier_files", {"files": []}),
    ],
)
def test_the_mcp_agent_cannot_reach_a_dossier_its_owner_cannot_see(
    client: TestClient, analyse: dict, world: dict, tool: str, extra: dict
) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)  # /a
    bob_token = _token_of(client, world["bob"])
    carol_token = _token_of(client, world["carol"])

    refused = client.portal.call(_call, bob_token, tool, {"dossier_id": dossier["id"], **extra})
    allowed = client.portal.call(_call, carol_token, tool, {"dossier_id": dossier["id"], **extra})

    assert refused == {"error": "Dossier introuvable", "status_code": 404}
    assert allowed.get("status_code") != 404


def test_the_mcp_agent_lists_only_the_dossiers_its_owner_sees(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        restricted = _create(client, analyse)
    bob_token = _token_of(client, world["bob"])
    alice_token = _token_of(client, world["alice"])

    def listed(token: str) -> set[str]:
        ids: set[str] = set()
        for page in range(1, 40):
            body = client.portal.call(_call, token, "list_dossiers", {"page": page, "page_size": 100})
            ids |= {d["id"] for d in body["items"]}
            if page >= body["pages"]:
                break
        return ids

    assert restricted["id"] in listed(alice_token)
    assert restricted["id"] not in listed(bob_token)


def test_a_dossier_created_by_the_mcp_agent_is_restricted_to_its_owners_groups(
    client: TestClient, analyse: dict, world: dict
) -> None:
    token = _token_of(client, world["alice"])

    created = client.portal.call(_call, token, "create_dossier", {"name": "Créé par MCP", "analyse_id": analyse["id"]})

    with As(world["alice"]):
        access = client.get(f"/api/dossiers/{created['id']}/access").json()
    with As(world["bob"]):
        assert client.get(f"/api/dossiers/{created['id']}").status_code == 404
    assert access["visibility"] == "restricted" and [g["path"] for g in access["groups"]] == [world["a"]]
