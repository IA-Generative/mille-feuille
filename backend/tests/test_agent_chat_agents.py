"""Interroger un agent de l'analyse dans le chat : le plan le choisit, il répond avec son prompt et ses outils. Le LLM
est simulé (celui de `test_agent_chat`), la base et Redis sont réels."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.agent import usage
from app.agent.analysis_agents import AnalysisAgent, conversation_prompt, synthesis_of
from app.agent.chat.planner import agents_guide, parse
from tests.test_agent_chat import Llm, Searcher, events, hit, messages, plan, run, use_searcher
from tests.test_conversation_tools import open_chat

JURIST = {"name": "Juriste", "prompt": "Tu analyses les clauses juridiques du bail.", "tools": [], "output": True}
ACCOUNTANT = {"name": "Comptable", "prompt": "Tu vérifies les montants et les charges.", "tools": [], "output": True}


@pytest.fixture(autouse=True)
def _no_dispatch_no_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.routers.dossiers.dispatch_chat_response", lambda *args: None)

    async def no_usage(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(usage, "record", no_usage)


def setup_chat(client: TestClient, agents: list[dict], question: str = "Que dit la clause de résiliation ?") -> dict:
    analyse = client.post("/api/analyses", json={"name": f"Agents {uuid.uuid4().hex[:6]}", "description": "T"}).json()
    for agent in agents:
        assert client.post(f"/api/analyses/{analyse['id']}/agents", json=agent).status_code == 201
    dossier_id, conversation_id = open_chat(client, analyse)
    client.post(
        f"/api/dossiers/{dossier_id}/documents", files=[("files", ("bail.pdf", b"fake-bytes", "application/pdf"))]
    )
    document = client.get(f"/api/dossiers/{dossier_id}").json()["documents"][0]
    page = client.post(
        f"/api/internal/documents/{document['id']}/pages",
        json={"page_number": 1, "content": "Résiliation avec un préavis de trois mois."},
        headers={"X-App-Token": "dev-only-worker-token-not-for-prod"},
    ).json()
    client.post(f"/api/dossiers/{dossier_id}/conversations/{conversation_id}/messages", json={"content": question})
    return {"dossier": dossier_id, "conversation": conversation_id, "document": document["id"], "page": page["id"]}


def test_the_plan_can_hand_the_question_to_an_agent_which_answers_with_its_prompt(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = setup_chat(client, [JURIST, ACCOUNTANT])
    llm = Llm(
        monkeypatch,
        completions=[
            plan(mode="agent", agent="1", standalone_query="clause de résiliation"),
            "La clause prévoit un préavis de trois mois.",
        ],
    )

    run(client, ids)

    planner_system = llm.requests[0]["messages"][0]["content"]
    assert "ref=1 nom=Juriste" in planner_system and "ref=2 nom=Comptable" in planner_system
    agent_system = llm.requests[1]["messages"][0]["content"]
    assert JURIST["prompt"] in agent_system and ACCOUNTANT["prompt"] not in agent_system
    assert "Tu n'as pas encore de synthèse" in agent_system
    # L'agent répond lui-même : pas d'appel de réponse en streaming.
    assert llm.stream_requests == []
    [*_, reply] = messages(client, ids)
    # Le nom de l'agent suit la réponse, en marqueur invisible que le frontend montre en étiquette.
    assert reply["role"] == "assistant"
    assert reply["content"] == "La clause prévoit un préavis de trois mois.\n\n<!--agent:Juriste-->"
    kinds = events(client, ids)
    assert ("thinking", {"agent": "Juriste"}) in kinds and kinds[-1][0] == "done"


def test_an_unknown_agent_falls_back_to_searching_the_dossier(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = setup_chat(client, [JURIST])
    use_searcher(monkeypatch, Searcher([hit(ids, "Résiliation avec un préavis de trois mois.")]))
    llm = Llm(
        monkeypatch,
        completions=[plan(mode="agent", agent="9")],
        streamed=["Trois mois de préavis."],
    )

    run(client, ids)

    assert len(llm.stream_requests) == 1
    [*_, reply] = messages(client, ids)
    assert reply["content"] == "Trois mois de préavis."


def test_an_analysis_without_agent_never_offers_the_agent_mode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = setup_chat(client, [])
    use_searcher(monkeypatch, Searcher([hit(ids, "Résiliation avec un préavis de trois mois.")]))
    llm = Llm(monkeypatch, completions=[plan(mode="agent", agent="1")], streamed=["Réponse."])

    run(client, ids)

    assert "Mode supplémentaire" not in llm.requests[0]["messages"][0]["content"]
    [*_, reply] = messages(client, ids)
    assert reply["content"] == "Réponse."


def test_the_agent_summary_is_the_beginning_of_its_prompt_on_one_line() -> None:
    long = AnalysisAgent("1", "Juriste", "Tu analyses\nles clauses. " * 40, [], None)
    assert "\n" not in long.summary and long.summary.endswith("…") and len(long.summary) <= 201
    assert AnalysisAgent("2", "Vide", "", [], None).summary == "(sans description)"
    assert agents_guide([]) == ""


def test_the_plan_of_an_agent_needs_a_known_reference() -> None:
    raw = plan(mode="agent", agent="2", standalone_query="clause")
    assert parse(raw, "q", frozenset({"1", "2"})).agent == "2"
    assert parse(raw, "q", frozenset({"1"})).mode == "search"
    assert parse(plan(mode="agent", standalone_query="clause"), "q", frozenset({"1"})).mode == "search"


def test_the_prompt_of_an_agent_carries_its_synthesis() -> None:
    agent = AnalysisAgent("1", "Juriste", "Rôle.", [], None)
    dossier = {"execution_steps": [{"kind": "agent", "label": "Juriste", "output": "Bail de trois ans."}]}
    synthesis = synthesis_of(dossier, agent)
    assert synthesis == "Bail de trois ans."
    assert "Bail de trois ans." in conversation_prompt(agent, synthesis, [])
    other = {"execution_steps": [{"kind": "agent", "label": "Comptable", "output": "Autre."}]}
    assert synthesis_of(other, agent) is None


def test_the_agent_marker_encodes_the_name_without_breaking_the_html_comment() -> None:
    from app.agent.chat.prompts import agent_marker

    assert agent_marker("Juriste") == "\n\n<!--agent:Juriste-->"
    marker = agent_marker("Agent -- n°2 > fin")
    assert "--" not in marker.removeprefix("\n\n<!--").removesuffix("-->") and ">" not in marker[:-3]
