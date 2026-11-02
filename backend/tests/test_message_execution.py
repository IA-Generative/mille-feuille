"""Le détail de l'exécution d'une réponse : ce que l'assistant a fait (plan, outils avec leurs arguments et leurs
résultats entiers, écarts du cas normal), gardé avec le message et montré dans une modale à côté des pouces."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.agent.chat.events import ChatEvents
from app.schemas.message_execution import MAX_ARGUMENTS_CHARS, MAX_RESULT_CHARS, MAX_STEPS
from tests.test_agent_chat import (  # noqa: F401  (la fixture automatique du chat simulé)
    CONTENT,
    Llm,
    Searcher,
    _no_dispatch_no_usage,
    hit,
    messages,
    plan,
    run,
    setup_chat,
    use_searcher,
)
from tests.test_agent_chat import events as chat_events


def test_a_searched_answer_carries_the_plan_the_search_and_its_full_result(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    long_text = CONTENT + " " + "Clause détaillée du bail. " * 30
    ids = setup_chat(client, long_text)
    use_searcher(monkeypatch, Searcher([hit(ids, long_text)]))
    Llm(
        monkeypatch,
        completions=[plan(mode="search", standalone_query="loyer", queries=["loyer mensuel"])],
        streamed=["Le loyer est de ", "800 euros [1]."],
    )

    run(client, ids)

    [*_, reply] = messages(client, ids)
    execution = reply["execution"]
    assert execution["mode"] == "search" and execution["model"] and execution["notes"] == []
    assert isinstance(execution["duration_ms"], int) and execution["duration_ms"] >= 0
    [step] = execution["steps"]
    assert step["tool_name"] == "search_documents" and step["arguments"] == {"query": "loyer mensuel"}
    # Le résultat entier, pas les 200 premiers caractères du flux.
    assert long_text in step["result"] and len(step["result"]) > 200


def test_the_full_result_never_goes_to_the_browser(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = setup_chat(client)
    use_searcher(monkeypatch, Searcher([hit(ids)]))
    Llm(monkeypatch, completions=[plan(mode="search", queries=["loyer"])], streamed=["800 euros."])

    run(client, ids)

    results = [data for kind, data in chat_events(client, ids) if kind == "tool_result"]
    assert results and all("full" not in data and len(data["preview"]) <= 203 for data in results)


def test_a_direct_answer_has_a_plan_and_no_step(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = setup_chat(client)
    use_searcher(monkeypatch, Searcher([hit(ids)]))
    Llm(monkeypatch, completions=[plan(mode="direct", answer="Bonjour !")])

    run(client, ids)

    execution = messages(client, ids)[-1]["execution"]
    assert execution["mode"] == "direct" and execution["steps"] == [] and execution["iterations"] is None


def test_a_fallback_on_the_tools_is_noted_with_its_calls_and_iterations(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = setup_chat(client)
    use_searcher(monkeypatch, Searcher([]))
    Llm(
        monkeypatch,
        completions=[plan(mode="search", queries=["loyer"]), ("read_page", {"page_number": 1}), "Il est de 800 €."],
    )

    run(client, ids)

    execution = messages(client, ids)[-1]["execution"]
    assert any("repli sur les outils" in note for note in execution["notes"])
    assert execution["iterations"] == 2
    read = next(step for step in execution["steps"] if step["tool_name"] == "read_page")
    assert read["arguments"] == {"page_number": 1} and CONTENT in read["result"]


def test_the_message_of_the_person_has_no_execution(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = setup_chat(client)
    use_searcher(monkeypatch, Searcher([hit(ids)]))
    Llm(monkeypatch, completions=[plan(mode="direct", answer="Bonjour !")])

    run(client, ids)

    [asked, answered] = messages(client, ids)[-2:]
    assert asked["role"] == "user" and asked["execution"] is None and answered["execution"] is not None


@pytest.mark.anyio
async def test_a_result_arguments_and_the_number_of_steps_are_bounded() -> None:
    trace = ChatEvents(str(uuid.uuid4()))

    await trace.emit("tool_call", {"tool_name": "lire", "arguments": {"texte": "x" * (MAX_ARGUMENTS_CHARS + 500)}})
    await trace.emit("tool_result", {"tool_name": "lire", "preview": "début", "full": "y" * (MAX_RESULT_CHARS + 500)})
    for number in range(MAX_STEPS + 5):
        await trace.emit("tool_call", {"tool_name": f"outil-{number}", "arguments": {}})

    execution = trace.execution()
    first = execution["steps"][0]
    assert list(first["arguments"]) == ["…"] and len(first["arguments"]["…"]) <= MAX_ARGUMENTS_CHARS + 10
    assert first["result"].endswith("[…]") and len(first["result"]) <= MAX_RESULT_CHARS + 10
    assert len(execution["steps"]) == MAX_STEPS and execution["omitted_steps"] == 6


@pytest.mark.anyio
async def test_a_result_goes_with_the_last_call_of_that_tool_that_has_none() -> None:
    trace = ChatEvents(str(uuid.uuid4()))

    await trace.emit("tool_call", {"tool_name": "lire", "arguments": {"n": 1}, "agent": "Agent 1"})
    await trace.emit("tool_result", {"tool_name": "lire", "preview": "un"})
    await trace.emit("tool_call", {"tool_name": "lire", "arguments": {"n": 2}})
    await trace.emit("tool_result", {"tool_name": "lire", "preview": "deux"})

    steps = trace.execution()["steps"]
    assert [(s["arguments"]["n"], s["result"], s["agent"]) for s in steps] == [(1, "un", "Agent 1"), (2, "deux", None)]


@pytest.mark.anyio
async def test_a_note_is_kept_once_and_is_not_an_event() -> None:
    trace = ChatEvents(str(uuid.uuid4()))

    await trace.emit("note", {"text": "Réponse redemandée."})
    trace.note("Réponse redemandée.")

    assert trace.execution()["notes"] == ["Réponse redemandée."] and trace.execution()["steps"] == []
