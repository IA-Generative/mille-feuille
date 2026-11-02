"""L'assistant de l'application dans le backend : le LLM est simulé, la base est réelle.

Les travaux tournent sur la boucle de l'application (`client.portal`), celle qui possède le moteur de base."""

import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agent import agent_loop, usage
from app.agent.helper.job import run_helper_chat
from app.agent.helper.tools import HelperTools


@pytest.fixture(autouse=True)
def _no_dispatch_no_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.routers.agent_conversations.dispatch_helper_chat_response", lambda *args, **kwargs: None)

    async def no_usage(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(usage, "record", no_usage)


class Llm:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, turns: list) -> None:
        self.turns = list(turns)
        self.requests: list[dict] = []
        llm = self

        async def complete(**kwargs: object) -> SimpleNamespace:
            llm.requests.append(kwargs)
            turn = llm.turns.pop(0)
            if isinstance(turn, Exception):
                raise turn
            calls, content = None, turn if isinstance(turn, str) else ""
            if isinstance(turn, tuple):
                name, arguments = turn
                calls = [
                    SimpleNamespace(id="call-1", function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))
                ]
            message = SimpleNamespace(content=content, tool_calls=calls)
            return SimpleNamespace(model="m", usage=None, choices=[SimpleNamespace(message=message)])

        monkeypatch.setattr(agent_loop.llm, "complete", complete)


def open_conversation(client: TestClient, text: str) -> str:
    conversation = client.post("/api/agent-conversations", json={}).json()
    response = client.post(f"/api/agent-conversations/{conversation['id']}/messages", json={"content": text})
    assert response.status_code == 200, response.text
    return conversation["id"]


def conversation(client: TestClient, conversation_id: str) -> dict:
    return client.get(f"/api/agent-conversations/{conversation_id}").json()


def acting_user(client: TestClient, conversation_id: str) -> str:
    return conversation(client, conversation_id)["created_by"]


def test_the_assistant_looks_for_an_analysis_then_answers_with_the_resources_it_touched(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = f"Analyse CNI {uuid.uuid4().hex[:6]}"
    analyse = client.post("/api/analyses", json={"name": name, "description": "Cartes d'identité"}).json()
    conversation_id = open_conversation(client, "Trouve-moi l'analyse CNI")
    llm = Llm(monkeypatch, [("search_analyses", {"q": name}), "Voici l'analyse CNI."])

    client.portal.call(run_helper_chat, conversation_id, None)

    # L'historique est le dialogue, et le résultat de l'outil nomme l'analyse trouvée.
    assert llm.requests[0]["messages"][1] == {"role": "user", "content": "Trouve-moi l'analyse CNI"}
    tool_message = llm.requests[1]["messages"][-1]
    assert tool_message["role"] == "tool" and f"{name} (id: {analyse['id']})" in tool_message["content"]
    messages = conversation(client, conversation_id)["messages"]
    reply = messages[-1]
    assert reply["role"] == "assistant" and reply["content"] == "Voici l'analyse CNI."
    assert [(s["analyse_id"], s["excerpt"]) for s in reply["sources"]] == [(analyse["id"], name)]
    with client.stream("GET", f"/api/agent-conversations/{conversation_id}/stream") as response:
        body = "".join(response.iter_text())
    kinds = [
        json.loads(line.removeprefix("data: "))["kind"]
        for line in body.splitlines()
        if "chat-event" not in line and line.startswith('data: {"')
    ]
    assert kinds == ["tool_call", "tool_result", "done"]


def test_a_failing_model_ends_the_conversation_with_an_error_event(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation_id = open_conversation(client, "Bonjour")
    Llm(monkeypatch, [RuntimeError("hub LLM indisponible")])

    client.portal.call(run_helper_chat, conversation_id, None)

    assert conversation(client, conversation_id)["messages"][-1]["role"] == "user"  # pas de réponse
    with client.stream("GET", f"/api/agent-conversations/{conversation_id}/stream") as response:
        body = "".join(response.iter_text())
    assert '"kind": "error"' in body and "hub LLM indisponible" in body


def test_the_assistant_creates_an_analysis_and_a_dossier_and_records_them(client: TestClient) -> None:
    conversation_id = open_conversation(client, "Crée-moi un dossier")
    user = acting_user(client, conversation_id)
    suffix = uuid.uuid4().hex[:6]

    async def scenario() -> tuple[HelperTools, str, str, str]:
        tools = HelperTools(user)
        created = await tools.create_analysis(f"Analyse créée {suffix}", "Objectif")
        analyse_id = created.split("id: ")[1].rstrip(").")
        dossier = await tools.create_dossier(f"Dossier créé {suffix}", analyse_id)
        dossier_id = dossier.split("id: ")[1].split(")")[0]
        return tools, analyse_id, dossier_id, await tools.get_dossier(dossier_id)

    tools, analyse_id, dossier_id, described = client.portal.call(scenario)

    assert f"Dossier « Dossier créé {suffix} » (id: {dossier_id})" in described and "Documents : 0" in described
    assert {(r.analyse_id, r.dossier_id) for r in tools.consulted_resources()} == {
        (analyse_id, None),
        (None, dossier_id),
    }
    assert client.get(f"/api/dossiers/{dossier_id}").status_code == 200


def test_bad_identifiers_and_unknown_resources_are_reported_to_the_model_not_raised(client: TestClient) -> None:
    async def scenario() -> list[str]:
        tools = HelperTools("someone")
        return [
            await tools.get_analysis("pas-un-uuid"),
            await tools.get_analysis(str(uuid.uuid4())),
            await tools.get_dossier("pas-un-uuid"),
            await tools.run_dossier(str(uuid.uuid4())),
            await tools.dispatch_tool("inconnu", {}),
        ]

    answers = client.portal.call(scenario)

    assert answers[0] == "Erreur : identifiant d'analyse invalide."
    assert answers[1].startswith("Erreur :") and answers[3].startswith("Erreur :")
    assert answers[2] == "Erreur : identifiant de dossier invalide."
    assert answers[4] == "Outil 'inconnu' inconnu."


def test_the_assistant_sees_only_the_dossiers_of_the_person(client: TestClient) -> None:
    conversation_id = open_conversation(client, "Mes dossiers ?")
    owner = acting_user(client, conversation_id)
    analyse = client.post("/api/analyses", json={"name": f"A {uuid.uuid4().hex[:6]}", "description": "T"}).json()
    dossier = client.post("/api/dossiers", json={"name": f"Privé {uuid.uuid4().hex[:6]}", "analyse_id": analyse["id"]})
    assert dossier.status_code == 201

    async def scenario() -> tuple[str, str]:
        return await HelperTools(owner).list_dossiers(), await HelperTools("une-personne-inconnue").list_dossiers()

    mine, stranger = client.portal.call(scenario)

    assert dossier.json()["name"] in mine
    assert dossier.json()["name"] not in stranger
