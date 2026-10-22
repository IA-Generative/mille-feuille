import asyncio
from types import SimpleNamespace

import fakeredis
import httpx2

from app.services.tools.call_limits import CallLimiter
from app.services.tools.call_result import MESSAGES, ToolCallOutcome, bound_output
from app.services.tools.mcp_caller import McpToolCaller, result_text


def test_a_short_output_is_kept_whole() -> None:
    assert bound_output("bonjour", 20) == ("bonjour", False)


def test_a_long_output_is_cut_and_flagged() -> None:
    text, truncated = bound_output("x" * 50, 20)
    assert (len(text), truncated) == (20, True)


def test_a_failure_carries_a_stable_code_and_a_french_message_for_the_model() -> None:
    outcome = ToolCallOutcome.failure("delai_depasse")
    assert (outcome.ok, outcome.code, outcome.output) == (False, "delai_depasse", MESSAGES["delai_depasse"])
    assert ToolCallOutcome.failure("session_requise", "Reconnectez-vous.").output == "Reconnectez-vous."


def test_text_blocks_are_joined_and_other_blocks_are_flagged_not_forwarded() -> None:
    content = [
        SimpleNamespace(type="text", text="un"),
        SimpleNamespace(type="image"),
        SimpleNamespace(type="text", text="deux"),
    ]
    assert result_text(content) == "un\n[contenu image non transmis]\ndeux"


def limiter(per_run: int = 2, per_minute: int = 100) -> CallLimiter:
    return CallLimiter(fakeredis.FakeRedis(decode_responses=True), per_run=per_run, per_minute=per_minute)


def test_a_run_cannot_exceed_its_quota() -> None:
    quota = limiter(per_run=2)
    allowed = [asyncio.run(quota.allow("alice", "run-1")) for _ in range(3)]
    assert allowed == [True, True, False]
    assert asyncio.run(quota.allow("alice", "run-2")) is True  # un autre run repart de zéro


def test_a_person_cannot_exceed_the_per_minute_quota_across_runs() -> None:
    quota = limiter(per_run=100, per_minute=3)
    allowed = [asyncio.run(quota.allow("alice", f"run-{i}")) for i in range(4)]
    assert allowed == [True, True, True, False]
    assert asyncio.run(quota.allow("bob", None)) is True


def test_the_real_client_calls_a_tool_of_a_real_mcp_server(client) -> None:
    """Le vrai client MCP contre le serveur MCP de la plateforme, en mémoire : handshake, session, `tools/call`."""
    from app.main import app

    token = client.post("/api/app-tokens", json={"name": "call-test"}).json()["token"]
    caller = McpToolCaller(transport=httpx2.ASGITransport(app=app))

    async def run():
        return await caller.call_tool(
            "http://testserver/mcp",
            {"Authorization": f"Bearer {token}"},
            "get_ephemeral_analysis",
            {"analyse_id": "00000000-0000-0000-0000-000000000000"},
            10.0,
        )

    # Dans la boucle du TestClient : le pool de connexions de l'application y est lié (comme tests/test_mcp.py).
    result = client.portal.call(run)

    assert "introuvable" in result.text
    assert result.is_error is False
