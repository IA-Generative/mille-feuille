"""Chaque agent lit son analyse (en lecture seule) et peut en interroger un autre. Le LLM est simulé, la base est
réelle."""

import pytest
from fastapi.testclient import TestClient

from app.agent.agent_call import FUNCTION_NAME, MAX_CALLS
from app.agent.analysis_reader import AnalysisReader
from app.agent.jobs.agents import run_agents
from tests.test_agent_agents import Llm, _dispatched, finish_upstream, steps_of  # noqa: F401  (fixture autouse)


def launched(client: TestClient, tools_by_agent: list[list[str]]) -> dict:
    """Un dossier lancé dont l'analyse a un agent par liste d'outils, nommés Agent 1, Agent 2..."""
    import uuid

    analyse = client.post(
        "/api/analyses", json={"name": f"Accès {uuid.uuid4().hex[:6]}", "description": "Cartes"}
    ).json()
    for rank, tools in enumerate(tools_by_agent, start=1):
        body = {"name": f"Agent {rank}", "prompt": f"Fais X{rank}", "tools": tools, "output": True}
        assert client.post(f"/api/analyses/{analyse['id']}/agents", json=body).status_code == 201
    dossier = client.post("/api/dossiers", json={"name": "D", "analyse_id": analyse["id"]}).json()
    client.post(
        f"/api/dossiers/{dossier['id']}/documents", files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))]
    )
    assert client.post(f"/api/dossiers/{dossier['id']}/launch").status_code == 200
    return client.get(f"/api/dossiers/{dossier['id']}").json()


def tool_names(request: dict) -> list[str]:
    return [tool["function"]["name"] for tool in request["tools"]]


def test_every_agent_reads_its_analysis_and_the_other_agents_syntheses(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    dossier = launched(client, [[], []])
    finish_upstream(client, dossier)
    llm = Llm(
        monkeypatch,
        [
            "Synthèse de l'agent 1.",
            ("read_agent_output", {"agent": "Agent 1"}),
            ("read_analysis", {}),
            "Agent 2 a tout lu.",
        ],
    )

    client.portal.call(run_agents, dossier["id"], None)

    assert {"read_analysis", "list_agents", "read_agent_output", "view_analysis"} <= set(tool_names(llm.requests[0]))
    tool_results = [m["content"] for m in llm.requests[3]["messages"] if m["role"] == "tool"]
    assert tool_results[0] == "Synthèse de l'agent 1."
    assert "Objectif : Cartes" in tool_results[1] and "Agent 1" in tool_results[1] and "Agent 2" in tool_results[1]
    assert steps_of(client, dossier["id"])["Agent 2"]["output"] == "Agent 2 a tout lu."


def test_an_agent_asks_another_agent_and_gets_its_answer(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    dossier = launched(client, [["appel_agent"], []])
    finish_upstream(client, dossier)
    llm = Llm(
        monkeypatch,
        [
            (FUNCTION_NAME, {"agent": "Agent 2", "question": "Quel est le montant ?"}),
            "Le montant est de 800 euros.",  # l'agent 2 répond à l'agent 1
            "L'agent 2 dit : 800 euros.",  # l'agent 1 conclut
            "Synthèse de l'agent 2.",
        ],
    )

    client.portal.call(run_agents, dossier["id"], None)

    assert FUNCTION_NAME in tool_names(llm.requests[0])
    # L'agent interrogé travaille avec son prompt, la question de l'autre, et sans pouvoir en appeler un troisième.
    asked = llm.requests[1]
    assert asked["messages"][0]["content"].startswith("Fais X2")
    assert asked["messages"][-1] == {"role": "user", "content": "Quel est le montant ?"}
    assert FUNCTION_NAME not in tool_names(asked)
    assert llm.requests[2]["messages"][-1]["content"] == "Le montant est de 800 euros."
    steps = steps_of(client, dossier["id"])
    assert steps["Agent 1"]["output"] == "L'agent 2 dit : 800 euros."


def test_an_agent_cannot_ask_itself_nor_an_unknown_agent_nor_without_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    dossier = launched(client, [["appel_agent"], []])
    finish_upstream(client, dossier)
    asks = [
        (FUNCTION_NAME, {"agent": "Agent 1", "question": "Moi ?"}),
        (FUNCTION_NAME, {"agent": "Inconnu", "question": "?"}),
    ]
    calls = [(FUNCTION_NAME, {"agent": "Agent 2", "question": f"Q{i}"}) for i in range(MAX_CALLS + 1)]
    answers = [f"R{i}" for i in range(MAX_CALLS)]
    turns = [*asks, calls[0], answers[0], calls[1], answers[1], calls[2], answers[2], calls[3], "Fin.", "Synthèse 2."]
    llm = Llm(monkeypatch, turns)

    client.portal.call(run_agents, dossier["id"], None)

    results = [m["content"] for m in llm.requests[-2]["messages"] if m["role"] == "tool"]
    assert "inconnu" in results[0] and "inconnu" in results[1]  # soi-même : pas dans les agents interrogeables
    assert "Limite atteinte" in results[-1]
    assert steps_of(client, dossier["id"])["Agent 1"]["output"] == "Fin."


def test_without_the_tool_an_agent_cannot_ask_another(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    dossier = launched(client, [[], []])
    finish_upstream(client, dossier)
    llm = Llm(monkeypatch, ["Un.", "Deux."])

    client.portal.call(run_agents, dossier["id"], None)

    assert all(FUNCTION_NAME not in tool_names(request) for request in llm.requests)


def test_the_reader_reports_what_is_missing_instead_of_failing() -> None:
    reader = AnalysisReader(dossier={"id": "x", "execution_steps": []}, analyse_id=None, user_id="u")
    assert not reader.available and reader.definitions() == []
    assert "indisponible" in reader.read_analysis()
    assert "pas d'agent" in reader.list_agents()
    assert "Aucune synthèse" in reader.read_agent_output("Fantôme")
    pending = AnalysisReader(
        dossier={"id": "x", "execution_steps": [{"kind": "agent", "label": "Juriste", "output": None}]},
        analyse_id=None,
        user_id="u",
    )
    assert "pas encore produit" in pending.read_agent_output("juriste")


def test_the_chat_does_not_offer_the_agent_call_tool(client: TestClient) -> None:
    from tests.test_conversation_tools import analyse_with_tools, open_chat, tools_url

    dossier_id, conversation_id = open_chat(client, analyse_with_tools(client, ["calculatrice", "appel_agent"]))

    offered = client.get(tools_url(dossier_id, conversation_id)).json()

    assert [tool["id"] for tool in offered["tools"]] == ["calculatrice"]
