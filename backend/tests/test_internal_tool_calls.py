import uuid

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import async_session_factory
from app.main import app
from app.models.tool import ToolCallLog
from app.routers.internal_tools import get_call_limiter
from app.services.tools.call_limits import CallLimiter
from app.services.tools.mcp_caller import CallFailedError, CallTimeoutError, RawToolResult
from tests.access_support import As
from tests.tool_support import FakeCaller, FakeIdentityTokens, FakeLister, create_server, tool_id

TOKEN = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


def call(client: TestClient, tool: str, *, person=None, arguments: dict | None = None, run_id: str | None = None):
    headers = {**TOKEN, **({"X-Acting-User": person.user_id} if person else {})}
    body = {"arguments": arguments or {"mots_cles": "subvention"}, "run_id": run_id or f"run-{uuid.uuid4().hex[:8]}"}
    return client.post(f"/api/internal/tools/{tool}/call", json=body, headers=headers)


def logs_of(client: TestClient, user_id: str) -> list[ToolCallLog]:
    async def read() -> list[ToolCallLog]:
        async with async_session_factory() as session:
            return list(
                (
                    await session.execute(
                        select(ToolCallLog).where(ToolCallLog.user_id == user_id).order_by(ToolCallLog.created_at)
                    )
                ).scalars()
            )

    return client.portal.call(read)


@pytest.fixture
def server(client: TestClient, lister: FakeLister, world: dict) -> dict:
    with As(world["alice"]):
        return create_server(client, visibility="all")


def test_a_tool_is_called_for_the_person_and_only_its_output_comes_back(
    client: TestClient, caller: FakeCaller, server: dict, world: dict
) -> None:
    response = call(client, tool_id(server, "rechercher_texte"), person=world["bob"])

    assert response.status_code == 200
    body = response.json()
    assert (body["ok"], body["code"], body["output"]) == (True, None, "Article L1111-1 : …")
    assert body["untrusted"] is True
    assert caller.calls[0][2:] == ("rechercher_texte", {"mots_cles": "subvention"})
    assert caller.calls[0][1] == {}  # serveur sans authentification : aucun jeton


def test_the_token_for_the_person_is_added_by_the_backend_never_asked_of_the_worker(
    client: TestClient, caller: FakeCaller, lister: FakeLister, identity_tokens: FakeIdentityTokens, world: dict
) -> None:
    with As(world["alice"]):
        server = create_server(client, visibility="all", auth_mode="token_exchange", audience="mcp-legifrance")

    call(client, tool_id(server, "rechercher_texte"), person=world["bob"])

    assert caller.calls[0][1] == {"Authorization": "Bearer exchanged-for-mcp-legifrance"}
    assert identity_tokens.calls[-1] == (world["bob"].user_id, "mcp-legifrance")


def test_without_a_person_an_identity_server_answers_with_a_clear_code(
    client: TestClient, caller: FakeCaller, lister: FakeLister, identity_tokens: FakeIdentityTokens, world: dict
) -> None:
    with As(world["alice"]):
        server = create_server(client, visibility="all", auth_mode="token_exchange", audience="mcp-legifrance")

    body = call(client, tool_id(server, "rechercher_texte")).json()

    assert (body["ok"], body["code"]) == (False, "identite_absente")
    assert caller.calls == []


def test_a_server_the_person_cannot_see_answers_unknown(
    client: TestClient, caller: FakeCaller, lister: FakeLister, world: dict
) -> None:
    with As(world["alice"]):
        private = create_server(client, visibility="private")

    body = call(client, tool_id(private, "rechercher_texte"), person=world["bob"]).json()

    assert (body["ok"], body["code"]) == (False, "outil_inconnu")
    assert caller.calls == []


def test_a_tool_the_owner_did_not_authorize_is_not_called(
    client: TestClient, caller: FakeCaller, lister: FakeLister, world: dict
) -> None:
    with As(world["alice"]):
        shared = create_server(client, visibility="all", tools=["rechercher_texte"])

    body = call(client, tool_id(shared, "lire_article"), person=world["alice"]).json()

    assert body["code"] == "outil_desactive"
    assert caller.calls == []


@pytest.mark.parametrize(
    ("tool", "code"),
    [("calculatrice", "outil_interne"), ("fantome", "outil_inconnu"), (str(uuid.uuid4()), "outil_inconnu")],
)
def test_internal_and_unknown_tools_are_not_proxied(
    client: TestClient, caller: FakeCaller, tool: str, code: str
) -> None:
    body = call(client, tool).json()

    assert (body["ok"], body["code"]) == (False, code)
    assert caller.calls == []


@pytest.mark.parametrize(
    ("failure", "code"),
    [(CallTimeoutError(), "delai_depasse"), (CallFailedError(), "serveur_indisponible")],
)
def test_a_server_that_fails_gives_a_stable_code(
    client: TestClient, caller: FakeCaller, server: dict, world: dict, failure: Exception, code: str
) -> None:
    caller.result = failure

    body = call(client, tool_id(server, "rechercher_texte"), person=world["bob"]).json()

    assert (body["ok"], body["code"]) == (False, code)


def test_a_tool_that_answers_with_an_error_is_reported_with_its_message(
    client: TestClient, caller: FakeCaller, server: dict, world: dict
) -> None:
    caller.result = RawToolResult(text="Article introuvable", is_error=True)

    body = call(client, tool_id(server, "rechercher_texte"), person=world["bob"]).json()

    assert (body["ok"], body["code"], body["output"]) == (False, "outil_en_erreur", "Article introuvable")


def test_a_huge_output_is_cut(client: TestClient, caller: FakeCaller, server: dict, world: dict) -> None:
    caller.result = RawToolResult(text="x" * 30_000, is_error=False)

    body = call(client, tool_id(server, "rechercher_texte"), person=world["bob"]).json()

    assert (len(body["output"]), body["truncated"]) == (20_000, True)


def test_huge_arguments_are_refused_before_any_call(client: TestClient, caller: FakeCaller, server: dict) -> None:
    body = call(client, tool_id(server, "rechercher_texte"), arguments={"texte": "x" * 60_000}).json()

    assert body["code"] == "arguments_trop_longs"
    assert caller.calls == []


def test_the_run_quota_stops_the_calls(client: TestClient, caller: FakeCaller, server: dict, world: dict) -> None:
    limiter = CallLimiter(fakeredis.FakeRedis(decode_responses=True), per_run=2, per_minute=100)
    app.dependency_overrides[get_call_limiter] = lambda: limiter
    try:
        codes = [
            call(client, tool_id(server, "rechercher_texte"), person=world["bob"], run_id="r1").json()["code"]
            for _ in range(3)
        ]
    finally:
        del app.dependency_overrides[get_call_limiter]

    assert codes == [None, None, "quota_depasse"]
    assert len(caller.calls) == 2


def test_an_address_that_became_private_is_refused_at_call_time(
    client: TestClient, caller: FakeCaller, server: dict, world: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.tools.url_guard._system_resolver", lambda host: ["169.254.169.254"])

    body = call(client, tool_id(server, "rechercher_texte"), person=world["bob"]).json()

    assert body["code"] == "adresse_refusee"
    assert caller.calls == []


def test_every_call_is_logged_without_its_arguments_or_output(
    client: TestClient, caller: FakeCaller, server: dict, world: dict
) -> None:
    bob = world["bob"]
    call(client, tool_id(server, "rechercher_texte"), person=bob, run_id="journal")
    caller.result = CallTimeoutError()
    call(client, tool_id(server, "rechercher_texte"), person=bob, run_id="journal")

    logs = logs_of(client, bob.user_id)

    assert [(log.tool_name, log.server_name, log.outcome, log.run_id) for log in logs] == [
        ("rechercher_texte", server["name"], "ok", "journal"),
        ("rechercher_texte", server["name"], "delai_depasse", "journal"),
    ]
    assert all(log.duration_ms >= 0 for log in logs)
    assert not hasattr(logs[0], "arguments") and not hasattr(logs[0], "output")


def test_the_route_requires_the_worker_token(client: TestClient) -> None:
    assert client.post("/api/internal/tools/x/call", json={}).status_code == 422
    assert client.post("/api/internal/tools/x/call", json={}, headers={"X-App-Token": "nope"}).status_code == 401


# --- La résolution des définitions, pour le worker ---


def resolve(client: TestClient, ids: list[str], *, person=None):
    headers = {**TOKEN, **({"X-Acting-User": person.user_id} if person else {})}
    return client.post("/api/internal/tools/resolve", json={"tool_ids": ids}, headers=headers)


def test_the_worker_gets_the_definitions_the_person_can_use(
    client: TestClient, lister: FakeLister, server: dict, world: dict
) -> None:
    ids = [tool_id(server, "rechercher_texte"), tool_id(server, "lire_article")]

    body = resolve(client, ids, person=world["bob"]).json()

    assert [t["name"] for t in body["tools"]] == ["rechercher_texte", "lire_article"]
    assert body["unavailable"] == []
    assert body["tools"][0]["server_name"] == server["name"]
    assert body["tools"][0]["input_schema"] == {}  # aucun schéma annoncé par le faux serveur
    assert body["tools"][0]["side_effect"] is False


def test_what_the_person_cannot_use_is_listed_not_returned(client: TestClient, lister: FakeLister, world: dict) -> None:
    with As(world["alice"]):
        shared = create_server(client, visibility="all", tools=["rechercher_texte"])
        private = create_server(client, visibility="private")
    ids = [
        tool_id(shared, "rechercher_texte"),  # utilisable
        tool_id(shared, "lire_article"),  # non autorisé par la personne qui a ajouté le serveur
        tool_id(private, "rechercher_texte"),  # serveur invisible pour bob
        str(uuid.uuid4()),  # inconnu
        "calculatrice",  # interne : pas un tool MCP
    ]

    body = resolve(client, ids, person=world["bob"]).json()

    assert [t["id"] for t in body["tools"]] == [ids[0]]
    assert body["unavailable"] == ids[1:]


def test_without_a_person_only_public_servers_are_resolved(client: TestClient, lister: FakeLister, world: dict) -> None:
    with As(world["alice"]):
        private = create_server(client, visibility="private")

    body = resolve(client, [tool_id(private, "rechercher_texte")]).json()

    assert body["tools"] == [] and len(body["unavailable"]) == 1
