"""Les outils d'une conversation du chat : ceux que l'analyse autorise, moins ceux que la personne a retirés, appelés
en son nom. Un outil qui modifie des données n'est pas donné tant qu'aucune confirmation n'existe."""

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
    assert not any(name.endswith("_envoyer_courriel") for name in given)  # pas de confirmation : jamais donné
    assert {"search_documents", "read_page", "view_classifications", "view_entities"} <= set(given)  # le socle
    resolve = next(r for r in seen["requests"] if r.url.path.endswith("/tools/resolve"))
    assert resolve.headers["X-Acting-User"] == "alice"
    assert json.loads(resolve.content) == {"tool_ids": [READ_ONLY_ID, WRITING_ID]}


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
