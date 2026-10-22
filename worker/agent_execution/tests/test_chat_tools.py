"""Les outils d'une conversation du chat : ceux que l'analyse autorise, moins ceux que la personne a retirés, appelés
en son nom. Un outil qui modifie des données est donné, mais son appel attend l'accord de la personne."""

import json
import uuid

import httpx

from app import api_client
from app.agent_tool_set import build_extra_tools
from app.tasks import chat as chat_mod

READ_ONLY_ID = str(uuid.uuid4())
WRITING_ID = str(uuid.uuid4())


def definition(tool_id: str, name: str, *, side_effect: bool) -> dict:
    return {
        "id": tool_id,
        "name": name,
        "description": "Un outil.",
        "server_name": "Annuaire",
        "side_effect": side_effect,
        "input_schema": {},
    }


RESOLVED = {
    "tools": [
        definition(READ_ONLY_ID, "trouver_service", side_effect=False),
        definition(WRITING_ID, "envoyer_courriel", side_effect=True),
    ],
    "unavailable": [],
}


def client_for(handler) -> httpx.Client:
    return httpx.Client(base_url="http://backend/api/internal", transport=httpx.MockTransport(handler))


def names(extra) -> list[str]:
    return [d["function"]["name"] for d in extra.definitions()]


def test_a_tool_that_modifies_data_is_withheld_when_nothing_asks_for_confirmation() -> None:
    client = client_for(lambda request: httpx.Response(200, json=RESOLVED))

    extra = build_extra_tools(
        client, [READ_ONLY_ID, WRITING_ID], acting_user="alice", run_id="r", allow_side_effects=False
    )

    assert [n.split("_", 2)[2] for n in names(extra)] == ["trouver_service"]
    assert extra.withheld == [WRITING_ID]


def test_an_agent_keeps_the_tools_that_modify_data_by_default() -> None:
    client = client_for(lambda request: httpx.Response(200, json=RESOLVED))

    extra = build_extra_tools(client, [READ_ONLY_ID, WRITING_ID], acting_user="alice", run_id="r")

    assert len(names(extra)) == 2 and extra.withheld == []


def run_chat_task(monkeypatch, conversation_extra: dict) -> dict:
    """Exécute la tâche de chat ; `run_chat_graph` est remplacé par un faux qui garde ce qu'on lui a donné."""
    seen: dict = {"requests": [], "tools": None}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["requests"].append(request)
        path = request.url.path
        if path.endswith("/conversations/conv-1"):
            conversation = {
                "id": "conv-1",
                "dossier_id": "dossier-1",
                "user_id": "alice",
                "model": None,
                "messages": [{"id": "m1", "role": "user", "content": "Bonjour"}],
            }
            return httpx.Response(200, json=conversation | conversation_extra)
        if path.endswith("/dossiers/dossier-1"):
            return httpx.Response(200, json={"id": "dossier-1", "documents": [], "execution_steps": []})
        if path.endswith("/dossiers/dossier-1/notes"):
            return httpx.Response(200, json=[])
        if path.endswith("/tools/resolve"):
            return httpx.Response(200, json=RESOLVED)
        if path.endswith("/chat-events"):
            return httpx.Response(201, json={"id": "e1", "kind": "done", "data": {}, "created_at": ""})
        if path.endswith("/messages"):
            return httpx.Response(200, json={"id": "m2", "role": "assistant", "content": "ok", "sources": []})
        return httpx.Response(404)

    monkeypatch.setattr(api_client, "get_client", lambda: client_for(handler))

    def fake_chat(*, conversation_history, tools, **kwargs):
        seen["tools"] = tools
        return "Réponse", []

    monkeypatch.setattr(chat_mod, "run_chat_graph", fake_chat)
    chat_mod.run_chat.run("conv-1", "dossier-1")
    return seen


def test_the_chat_gives_the_tools_of_the_conversation_in_the_name_of_its_author(monkeypatch) -> None:
    seen = run_chat_task(monkeypatch, {"tool_ids": ["calculatrice", READ_ONLY_ID, WRITING_ID]})

    given = [d["function"]["name"] for d in seen["tools"].tool_definitions()]
    assert "calculer" in given  # la calculatrice
    assert any(name.endswith("_trouver_service") for name in given)  # un tool MCP en lecture seule
    writing = next(name for name in given if name.endswith("_envoyer_courriel"))  # donné, mais à confirmer
    assert seen["tools"].requires_confirmation(writing)
    assert not seen["tools"].requires_confirmation(next(n for n in given if n.endswith("_trouver_service")))
    assert {"search_documents", "read_page", "view_classifications", "view_entities"} <= set(given)  # le socle
    resolve = next(r for r in seen["requests"] if r.url.path.endswith("/tools/resolve"))
    assert resolve.headers["X-Acting-User"] == "alice"
    assert json.loads(resolve.content) == {"tool_ids": [READ_ONLY_ID, WRITING_ID]}


# --- Confirmation avant un outil qui modifie des données (#342) ---


class _ScriptedLLM:
    def __init__(self, calls: list[tuple[str, dict]], content: str = "") -> None:
        from types import SimpleNamespace as NS

        message = NS(
            content=content,
            tool_calls=[
                NS(id=f"call-{i}", function=NS(name=name, arguments=json.dumps(args)))
                for i, (name, args) in enumerate(calls)
            ],
        )
        self.chat = self
        self.completions = self
        self._reply = NS(choices=[NS(message=message)])
        self.requests = 0

    def create(self, **kwargs):
        self.requests += 1
        return self._reply


def _tools_with_writing_tool(calls_log: list):
    from app.tools import AgentTools

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tools/resolve"):
            return httpx.Response(200, json=RESOLVED)
        calls_log.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "code": None, "output": "fait"})

    extra = build_extra_tools(
        client_for(handler), [READ_ONLY_ID, WRITING_ID], acting_user="alice", run_id="r", confirm_side_effects=True
    )
    return AgentTools({"documents": [], "execution_steps": []}, extra=extra), extra


def _function_name(extra, suffix: str) -> str:
    return next(n for n in names(extra) if n.endswith(suffix))


def test_the_chat_stops_at_a_tool_that_modifies_data_and_runs_nothing_for_it(monkeypatch) -> None:
    from app import chat_graph

    backend_calls: list = []
    tools, extra = _tools_with_writing_tool(backend_calls)
    writing, reading = _function_name(extra, "_envoyer_courriel"), _function_name(extra, "_trouver_service")
    llm = _ScriptedLLM([(reading, {}), (writing, {"a": "bob"})], content="Je préviens Bob.")
    monkeypatch.setattr(chat_graph, "_client", lambda: llm)

    answer, _ = chat_graph.run_chat(conversation_history=[{"role": "user", "content": "Préviens Bob"}], tools=tools)

    assert answer == "Je préviens Bob." and llm.requests == 1  # le graphe s'arrête : le modèle n'est pas relancé
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
    assert len(backend_calls) == 1 and backend_calls[0]["arguments"] == {}  # seul l'outil en lecture a été appelé


def test_at_most_five_calls_are_kept_for_one_confirmation(monkeypatch) -> None:
    from app import chat_graph

    tools, extra = _tools_with_writing_tool([])
    writing = _function_name(extra, "_envoyer_courriel")
    monkeypatch.setattr(chat_graph, "_client", lambda: _ScriptedLLM([(writing, {"n": i}) for i in range(7)]))

    answer, _ = chat_graph.run_chat(conversation_history=[{"role": "user", "content": "x"}], tools=tools)

    assert len(tools.confirmation_batch) == 5
    assert answer == chat_graph.CONFIRMATION_TEXT  # un message sans texte reçoit une phrase d'accompagnement


def _conversation_with(calls: list[dict]) -> dict:
    return {
        "messages": [
            {"id": "m1", "role": "user", "content": "Préviens Bob", "tool_calls": []},
            {"id": "m2", "role": "assistant", "content": "Je préviens Bob.", "tool_calls": calls},
        ]
    }


def _stored_call(status: str, result: str | None, **fields) -> dict:
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
    conversation = _conversation_with(
        [
            _stored_call("executed", "fait"),
            _stored_call("refused", "Refusé par la personne.", id="tc-2", llm_call_id="call-2"),
            _stored_call("superseded", None, id="tc-3", llm_call_id="call-3"),
        ]
    )

    history = chat_mod._build_conversation_history(conversation)

    assert [m["role"] for m in history] == ["user", "assistant", "tool", "tool", "tool"]
    assert [c["id"] for c in history[1]["tool_calls"]] == ["call-1", "call-2", "call-3"]
    assert json.loads(history[1]["tool_calls"][0]["function"]["arguments"]) == {"a": "bob"}
    assert [m["tool_call_id"] for m in history[2:]] == ["call-1", "call-2", "call-3"]
    assert history[2]["content"] == "fait" and history[3]["content"] == "Refusé par la personne."
    assert history[4]["content"] == chat_mod.NO_DECISION


def test_approved_calls_run_with_the_arguments_the_person_saw_and_their_result_is_recorded() -> None:
    posted: list = []
    backend_calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tools/resolve"):
            return httpx.Response(200, json=RESOLVED)
        if request.url.path.endswith("/result"):
            posted.append((request.url.path, json.loads(request.content)))
            return httpx.Response(200, json={})
        backend_calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"ok": True, "code": None, "output": "courriel envoyé"})

    client = client_for(handler)
    extra = build_extra_tools(client, [WRITING_ID], acting_user="alice", run_id="r", confirm_side_effects=True)
    from app.tools import AgentTools

    tools = AgentTools({"documents": [], "execution_steps": []}, extra=extra)
    writing = _function_name(extra, "_envoyer_courriel")
    conversation = _conversation_with([_stored_call("approved", None, function_name=writing)])
    events: list = []

    chat_mod._run_approved_calls(client, conversation, tools, lambda kind, data: events.append(kind))
    history = chat_mod._build_conversation_history(conversation)

    assert backend_calls == [(f"/api/internal/tools/{WRITING_ID}/call", {"arguments": {"a": "bob"}, "run_id": "r"})]
    assert posted == [("/api/internal/chat-tool-calls/tc-1/result", {"result": posted[0][1]["result"]})]
    assert "courriel envoyé" in posted[0][1]["result"] and events == ["tool_call", "tool_result"]
    assert history[-1]["role"] == "tool" and "courriel envoyé" in history[-1]["content"]


def test_an_approved_call_whose_tool_is_gone_is_not_run() -> None:
    posted: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        posted.append(request.url.path)
        return httpx.Response(200, json={})

    from app.tools import AgentTools

    conversation = _conversation_with([_stored_call("approved", None)])
    chat_mod._run_approved_calls(
        client_for(handler), conversation, AgentTools({"documents": [], "execution_steps": []}), lambda *a: None
    )

    assert posted == ["/api/internal/chat-tool-calls/tc-1/result"]
    assert conversation["messages"][1]["tool_calls"][0]["result"] == chat_mod.TOOL_GONE


def test_a_conversation_without_chosen_tools_has_exactly_the_usual_chat_tools(monkeypatch) -> None:
    seen = run_chat_task(monkeypatch, {})  # ancienne conversation : aucun tool_ids

    given = [d["function"]["name"] for d in seen["tools"].tool_definitions()]
    assert "calculer" not in given
    assert not any(r.url.path.endswith("/tools/resolve") for r in seen["requests"])


def test_the_chat_prompt_warns_about_external_outputs(monkeypatch) -> None:
    seen = run_chat_task(monkeypatch, {"tool_ids": [READ_ONLY_ID]})

    assert "données non fiables" in seen["tools"].extra_notice or "donnée non fiable" in seen["tools"].extra_notice


def test_the_chat_system_prompt_carries_the_notice_of_the_chosen_tools() -> None:
    from app import chat_graph

    prompt = chat_graph._build_system_prompt([], [], tools_notice="NOTICE-OUTILS")
    assert prompt.rstrip().endswith("NOTICE-OUTILS")
    assert "NOTICE-OUTILS" not in chat_graph._build_system_prompt([], [])
