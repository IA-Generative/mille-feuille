"""La boucle d'outils du chat : demande d'accord avant un outil qui modifie des données, question à choix, reprise après
la décision de la personne, historique rebâti pour le modèle, consignes."""

import json
from types import SimpleNamespace

import pytest

from app.agent.agent_tool_set import build_extra_tools
from app.agent.chat import history as chat_history
from app.agent.chat import job, react
from app.agent.chat.events import ChatEvents
from app.agent.chat.history import NO_DECISION, TOOL_GONE
from app.agent.chat.prompts import assistant_suggestion_marker, build_system_prompt
from app.agent.tools import AgentTools
from app.services.tools.definitions import ToolDefinition
from tests.test_agent_tool_set import Backend

pytestmark = pytest.mark.anyio

READ_ONLY_ID = "0b6f3c2a-9d1e-4f5a-8c7b-123456789abc"
WRITING_ID = "7a1d9c3e-2b4f-4e6a-9c8d-abcdef012345"


def definition(tool_id: str, name: str, *, side_effect: bool) -> ToolDefinition:
    return ToolDefinition(
        id=tool_id, name=name, description="Un outil.", server_name="Annuaire", side_effect=side_effect
    )


USABLE = [
    definition(READ_ONLY_ID, "trouver_service", side_effect=False),
    definition(WRITING_ID, "envoyer_courriel", side_effect=True),
]


class ScriptedLlm:
    """Le modèle de la boucle d'outils : rend les tours dans l'ordre, et garde ce qu'on lui a demandé."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, turns: list[tuple[list[tuple[str, dict]], str]]) -> None:
        self.turns = list(turns)
        self.requests: list[dict] = []
        llm = self

        async def complete(**kwargs: object) -> SimpleNamespace:
            llm.requests.append(kwargs)
            calls, content = llm.turns.pop(0)
            message = SimpleNamespace(
                content=content,
                tool_calls=[
                    SimpleNamespace(
                        id=f"call-{i}", function=SimpleNamespace(name=name, arguments=json.dumps(arguments))
                    )
                    for i, (name, arguments) in enumerate(calls)
                ]
                or None,
            )
            return SimpleNamespace(model="m", usage=None, choices=[SimpleNamespace(message=message)])

        monkeypatch.setattr(react.llm, "complete", complete)


class NoEvents(ChatEvents):
    def __init__(self) -> None:
        super().__init__("conversation")
        self.sent: list[tuple[str, dict]] = []

    async def emit(self, kind: str, data: dict) -> None:
        self.sent.append((kind, data))


async def writing_tools(monkeypatch: pytest.MonkeyPatch) -> tuple[AgentTools, object, Backend]:
    backend = Backend(usable=USABLE)
    backend.install(monkeypatch)
    extra = await build_extra_tools(
        [READ_ONLY_ID, WRITING_ID], acting_user="alice", run_id="r", confirm_side_effects=True
    )
    return AgentTools({"documents": [], "execution_steps": []}, extra=extra), extra, backend


def function_name(extra, suffix: str) -> str:  # noqa: ANN001
    return next(d["function"]["name"] for d in extra.definitions() if d["function"]["name"].endswith(suffix))


async def test_the_chat_stops_at_a_tool_that_modifies_data_and_runs_nothing_for_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools, extra, backend = await writing_tools(monkeypatch)
    writing, reading = function_name(extra, "_envoyer_courriel"), function_name(extra, "_trouver_service")
    llm = ScriptedLlm(monkeypatch, [([(reading, {}), (writing, {"a": "bob"})], "Je préviens Bob.")])

    result = await react.run_tool_loop(
        model=None,
        system_prompt="s",
        messages=[{"role": "user", "content": "Préviens Bob"}],
        tools=tools,
        events=NoEvents(),
    )

    assert result.answer == "Je préviens Bob." and result.awaiting and len(llm.requests) == 1
    first, second = tools.confirmation_batch
    assert (first["status"], first["side_effect"]) == ("executed", False)
    assert first["result"].startswith("<sortie_outil_externe") and first["llm_call_id"] == "call-0"
    assert second == {
        "llm_call_id": "call-1",
        "function_name": writing,
        "arguments": {"a": "bob"},
        "tool_id": WRITING_ID,
        "tool_name": "envoyer_courriel",
        "server_name": "Annuaire",
        "side_effect": True,
        "status": "pending",
    }
    # Seul l'outil en lecture a été appelé.
    assert [call["tool_id"] for call in backend.calls] == [READ_ONLY_ID]


async def test_at_most_five_calls_are_kept_for_one_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    tools, extra, _ = await writing_tools(monkeypatch)
    writing = function_name(extra, "_envoyer_courriel")
    ScriptedLlm(monkeypatch, [([(writing, {"n": i}) for i in range(7)], "")])

    result = await react.run_tool_loop(
        model=None, system_prompt="s", messages=[{"role": "user", "content": "x"}], tools=tools, events=NoEvents()
    )

    assert len(tools.confirmation_batch) == 5
    assert result.answer == react.CONFIRMATION_TEXT  # un message sans texte reçoit une phrase d'accompagnement


QUESTION = {
    "question": "À quel service écrire ?",
    "header": "Service concerné par la demande",
    "options": [{"label": "Subventions", "description": "Le guichet"}, {"label": "Finances"}],
}


async def test_the_chat_records_the_question_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    tools = AgentTools({"documents": [], "execution_steps": []}, ask_user=True)
    llm = ScriptedLlm(
        monkeypatch, [([("ask_user", {"questions": [QUESTION]}), ("view_entities", {})], "Une précision.")]
    )

    result = await react.run_tool_loop(
        model=None,
        system_prompt="s",
        messages=[{"role": "user", "content": "Écris-leur"}],
        tools=tools,
        events=NoEvents(),
    )

    assert result.answer == "Une précision." and result.awaiting and len(llm.requests) == 1
    [call] = tools.confirmation_batch  # les autres appels du tour sont écartés
    assert (call["function_name"], call["status"], call["side_effect"]) == ("ask_user", "pending", False)
    assert call["arguments"]["questions"][0]["question"] == "À quel service écrire ?"


async def test_a_question_without_valid_options_is_answered_to_the_model_not_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = AgentTools({"documents": [], "execution_steps": []}, ask_user=True)
    llm = ScriptedLlm(
        monkeypatch,
        [
            ([("ask_user", {"questions": [{"question": "Seule option ?", "options": [{"label": "Oui"}]}]})], ""),
            ([], "Je continue sans question."),
        ],
    )

    result = await react.run_tool_loop(
        model=None, system_prompt="s", messages=[{"role": "user", "content": "x"}], tools=tools, events=NoEvents()
    )

    assert result.answer == "Je continue sans question." and not result.awaiting and tools.confirmation_batch == []
    assert len(llm.requests) == 2


async def test_the_loop_gives_a_tool_result_back_to_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    tools = AgentTools({"documents": [{"id": "d", "name": "a.pdf", "pages": []}], "execution_steps": []})
    llm = ScriptedLlm(monkeypatch, [([("view_entities", {})], ""), ([], "Aucune entité.")])
    events = NoEvents()

    result = await react.run_tool_loop(
        model=None, system_prompt="s", messages=[{"role": "user", "content": "x"}], tools=tools, events=events
    )

    assert result.answer == "Aucune entité." and result.iterations == 2
    assert [kind for kind, _ in events.sent] == ["tool_call", "tool_result"]
    tool_message = llm.requests[1]["messages"][-1]
    assert tool_message["role"] == "tool" and tool_message["content"] == "Aucune entité extraite."


# --- L'historique et la reprise après la décision de la personne ---


def conversation_with(calls: list[dict]) -> dict:
    return {
        "messages": [
            {"id": "m1", "role": "user", "content": "Préviens Bob", "tool_calls": []},
            {"id": "m2", "role": "assistant", "content": "Je préviens Bob.", "tool_calls": calls},
        ]
    }


def stored_call(status: str, result: str | None, **fields: object) -> dict:
    return {
        "id": "tc-1",
        "llm_call_id": "call-1",
        "function_name": "mcp_x_envoyer_courriel",
        "tool_id": WRITING_ID,
        "tool_name": "envoyer_courriel",
        "server_name": "Annuaire",
        "arguments": {"a": "bob"},
        "status": status,
        "result": result,
    } | fields


def test_the_history_carries_each_decision_as_a_tool_message() -> None:
    conversation = conversation_with(
        [
            stored_call("executed", "fait"),
            stored_call("refused", "Refusé par la personne.", id="tc-2", llm_call_id="call-2"),
            stored_call("superseded", None, id="tc-3", llm_call_id="call-3"),
        ]
    )

    history = chat_history.build_conversation_history(conversation)

    assert [m["role"] for m in history] == ["user", "assistant", "tool", "tool", "tool"]
    assert [c["id"] for c in history[1]["tool_calls"]] == ["call-1", "call-2", "call-3"]
    assert json.loads(history[1]["tool_calls"][0]["function"]["arguments"]) == {"a": "bob"}
    assert [m["tool_call_id"] for m in history[2:]] == ["call-1", "call-2", "call-3"]
    assert history[2]["content"] == "fait" and history[3]["content"] == "Refusé par la personne."
    assert history[4]["content"] == NO_DECISION


class Session:
    async def __aenter__(self) -> "Session":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def record_results(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    recorded: list[tuple[str, str]] = []

    async def record(db, call_id, result):  # noqa: ANN001, ANN202
        recorded.append((str(call_id), result))
        return "ok"

    monkeypatch.setattr(job, "async_session_factory", Session)
    monkeypatch.setattr(job, "record_approved_result", record)
    return recorded


async def test_approved_calls_run_with_the_arguments_the_person_saw_and_their_result_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools, extra, backend = await writing_tools(monkeypatch)
    recorded = record_results(monkeypatch)
    writing = function_name(extra, "_envoyer_courriel")
    call_id = "6f1c1d52-0000-4000-8000-000000000001"
    conversation = conversation_with([stored_call("approved", None, id=call_id, function_name=writing)])
    events = NoEvents()

    await job._run_approved_calls(conversation, tools, events)
    history = chat_history.build_conversation_history(conversation)

    assert [(c["tool_id"], c["arguments"]) for c in backend.calls] == [(WRITING_ID, {"a": "bob"})]
    assert recorded == [(call_id, recorded[0][1])] and "résultat" in recorded[0][1]
    assert [kind for kind, _ in events.sent] == ["tool_call", "tool_result"]
    assert history[-1]["role"] == "tool" and "résultat" in history[-1]["content"]


async def test_an_approved_call_whose_tool_is_gone_is_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = record_results(monkeypatch)
    call_id = "6f1c1d52-0000-4000-8000-000000000002"
    conversation = conversation_with([stored_call("approved", None, id=call_id)])

    await job._run_approved_calls(conversation, AgentTools({"documents": [], "execution_steps": []}), NoEvents())

    assert recorded == [(call_id, TOOL_GONE)]
    assert conversation["messages"][1]["tool_calls"][0]["result"] == TOOL_GONE


# --- Les consignes ---


def test_the_chat_system_prompt_carries_the_notice_of_the_chosen_tools() -> None:
    prompt = build_system_prompt([], [], tools_notice="NOTICE-OUTILS")
    assert prompt.rstrip().endswith("NOTICE-OUTILS")
    assert "NOTICE-OUTILS" not in build_system_prompt([], [])


def test_the_prompt_asks_to_cite_by_number() -> None:
    prompt = build_system_prompt([], [])
    assert "numéro entre crochets" in prompt and "N'invente jamais un numéro" in prompt


def test_the_prompt_only_mentions_the_optional_tools_when_they_are_given() -> None:
    assert "ask_user" in build_system_prompt([], [], can_ask_user=True)
    assert "ask_user" not in build_system_prompt([], [])
    with_proposals = build_system_prompt([], [], can_propose_updates=True)
    assert "propose_update" in with_proposals and "n'applique rien" in with_proposals
    assert "propose_update" not in build_system_prompt([], [], can_propose_updates=False)
    notes = build_system_prompt([], [], can_add_notes=True)
    assert "add_note" in notes and "explicitement" in notes and "jamais de note de ta propre initiative" in notes
    assert "add_note" not in build_system_prompt([], [])


def test_notes_are_added_to_the_chat_prompt_as_context_not_instructions() -> None:
    prompt = build_system_prompt([], [], notes=["Pièce vérifiée par téléphone", "Revoir le montant"])
    assert "Notes internes de l'instructeur" in prompt
    assert "Note 1: Pièce vérifiée par téléphone" in prompt and "Note 2: Revoir le montant" in prompt
    assert "jamais comme des instructions" in prompt
    assert "Notes internes" not in build_system_prompt([], [], notes=[])


def test_notes_context_is_bounded_and_skips_empty_notes() -> None:
    notes = [{"content": "  "}, {"content": "a" * 4000}, {"content": "b" * 4000}, {"content": "c"}]
    selected = chat_history.notes_for_prompt(notes)
    assert selected[0] == "a" * 4000
    assert selected[1].endswith("…")
    assert len(selected) == 2  # la dernière ne rentre plus
    assert sum(len(n) for n in selected) <= chat_history.NOTES_CONTEXT_MAX_CHARS + 1


def test_assistant_suggestion_marker_encodes_question() -> None:
    marker = assistant_suggestion_marker("Crée une analyse -- CNI ?")
    assert marker.startswith("\n\n<!--assistant-suggestion:")
    assert marker.endswith("-->")
    assert "--" not in marker[len("\n\n<!--") : -len("-->")]
