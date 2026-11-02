"""L'exécution des agents d'une analyse dans le backend : le LLM est simulé, la base est réelle.

Les travaux tournent sur la boucle de l'application (`client.portal`), celle qui possède le moteur de base."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agent import agent_loop, usage
from app.agent.jobs import agents as agents_job
from app.agent.jobs.agents import run_agents
from app.agent.runner import agent_runner

INTERNAL = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


@pytest.fixture(autouse=True)
def _dispatched(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Rien ne part vraiment : ni les workers de classification et d'extraction, ni le résumé du dossier."""
    sent: dict[str, list] = {"summary": []}
    for name in ("dispatch_classification", "dispatch_entity_extraction", "dispatch_agent_execution"):
        monkeypatch.setattr(f"app.routers.dossiers.{name}", lambda *args: None)
    monkeypatch.setattr(agents_job, "dispatch_dossier_summary", lambda dossier_id: sent["summary"].append(dossier_id))

    async def no_usage(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(usage, "record", no_usage)
    monkeypatch.setattr(agents_job, "POLL_INTERVAL", 0.05)
    return sent


class Llm:
    """Le modèle de l'agent : rend les tours dans l'ordre (une réponse, ou un appel d'outil), et garde les demandes."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, turns: list) -> None:
        self.turns = list(turns)
        self.requests: list[dict] = []
        llm = self

        async def complete(**kwargs: object) -> SimpleNamespace:
            llm.requests.append(kwargs)
            turn = llm.turns.pop(0)
            if isinstance(turn, Exception):
                raise turn
            calls = None
            content = turn if isinstance(turn, str) else ""
            if isinstance(turn, tuple):
                name, arguments = turn
                calls = [
                    SimpleNamespace(id="call-1", function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))
                ]
            message = SimpleNamespace(content=content, tool_calls=calls)
            return SimpleNamespace(model="m", usage=None, choices=[SimpleNamespace(message=message)])

        monkeypatch.setattr(agent_loop.llm, "complete", complete)


def launched_dossier(client: TestClient, name: str, *, tools: list[str] | None = None, agents: int = 1) -> dict:
    analyse = client.post("/api/analyses", json={"name": f"Analyse {name}", "description": "T"}).json()
    for index in range(agents):
        response = client.post(
            f"/api/analyses/{analyse['id']}/agents",
            json={"name": f"Agent {index + 1}", "prompt": f"Fais X{index + 1}", "tools": tools or [], "output": True},
        )
        assert response.status_code == 201
    dossier = client.post("/api/dossiers", json={"name": name, "analyse_id": analyse["id"]}).json()
    client.post(
        f"/api/dossiers/{dossier['id']}/documents", files=[("files", ("cni.pdf", b"fake-bytes", "application/pdf"))]
    )
    assert client.post(f"/api/dossiers/{dossier['id']}/launch").status_code == 200
    return client.get(f"/api/dossiers/{dossier['id']}").json()


def steps_of(client: TestClient, dossier_id: str) -> dict[str, dict]:
    return {s["label"]: s for s in client.get(f"/api/dossiers/{dossier_id}").json()["execution_steps"]}


def finish_upstream(client: TestClient, dossier: dict) -> None:
    """La classification et l'extraction, menées par leurs workers, se terminent."""
    for step in dossier["execution_steps"]:
        if step["kind"] in ("classification", "extraction"):
            body = {"status": "terminé", "output": None}
            assert client.post(f"/api/internal/execution-steps/{step['id']}/complete", json=body, headers=INTERNAL)


def run(client: TestClient, dossier: dict, acting_user: str | None = None) -> None:
    client.portal.call(run_agents, dossier["id"], acting_user)


def test_an_agent_runs_and_its_synthesis_completes_its_step(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, _dispatched: dict
) -> None:
    dossier = launched_dossier(client, "Agent simple")
    finish_upstream(client, dossier)
    llm = Llm(monkeypatch, ["Le dossier est cohérent."])

    run(client, dossier)

    agent = steps_of(client, dossier["id"])["Agent 1"]
    assert agent["status"] == "terminé" and agent["output"] == "Le dossier est cohérent."
    assert [log["message"] for log in agent["logs"]] == ["Agent 'Agent 1' démarré"]
    assert llm.requests[0]["messages"][0] == {"role": "system", "content": "Fais X1"}
    # Tout est terminé : le dossier aussi, et son résumé global part.
    assert client.get(f"/api/dossiers/{dossier['id']}").json()["status"] == "terminé"
    assert _dispatched["summary"] == [dossier["id"]]


def test_an_agent_uses_its_tools_before_concluding(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    dossier = launched_dossier(client, "Agent outils", tools=["calculatrice"])
    finish_upstream(client, dossier)
    llm = Llm(monkeypatch, [("calculer", {"expression": "2 + 2"}), "Le total est 4."])

    run(client, dossier)

    assert steps_of(client, dossier["id"])["Agent 1"]["output"] == "Le total est 4."
    tool_message = llm.requests[1]["messages"][-1]
    assert tool_message["role"] == "tool" and json.loads(tool_message["content"])["resultat"] == "4"
    assert "calculer" in [t["function"]["name"] for t in llm.requests[0]["tools"]]


def test_an_agent_that_fails_ends_in_failure_and_the_others_still_run(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, _dispatched: dict
) -> None:
    dossier = launched_dossier(client, "Agent en échec", agents=2)
    finish_upstream(client, dossier)
    Llm(monkeypatch, [RuntimeError("hub LLM indisponible"), "Second agent : tout va bien."])

    run(client, dossier)

    steps = steps_of(client, dossier["id"])
    assert steps["Agent 1"]["status"] == "échec" and steps["Agent 1"]["output"] == "hub LLM indisponible"
    assert [log["level"] for log in steps["Agent 1"]["logs"]] == ["info", "error"]
    assert steps["Agent 2"]["status"] == "terminé"
    assert _dispatched["summary"] == [dossier["id"]]


def test_the_agents_wait_for_the_classification_and_the_extraction(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    dossier = launched_dossier(client, "Agent attend")
    llm = Llm(monkeypatch, ["Terminé."])

    future = client.portal.start_task_soon(run_agents, dossier["id"], None)
    client.portal.call(asyncio.sleep, 0.3)
    assert llm.requests == [] and not future.done()  # rien ne part tant que les prédictions ne sont pas là

    finish_upstream(client, dossier)
    future.result(timeout=15)

    assert steps_of(client, dossier["id"])["Agent 1"]["output"] == "Terminé."


def test_the_agents_do_not_run_on_a_dossier_that_was_stopped(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, _dispatched: dict
) -> None:
    dossier = launched_dossier(client, "Agent arrêté")
    assert client.post(f"/api/dossiers/{dossier['id']}/stop").status_code == 200
    llm = Llm(monkeypatch, ["Ne doit pas servir."])

    run(client, dossier)

    assert llm.requests == [] and _dispatched["summary"] == []


def test_an_agent_already_finished_is_not_run_again(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    dossier = launched_dossier(client, "Agent déjà fait", agents=2)
    finish_upstream(client, dossier)
    first = steps_of(client, dossier["id"])["Agent 1"]
    body = {"status": "terminé", "output": "Déjà fait."}
    client.post(f"/api/internal/execution-steps/{first['id']}/complete", json=body, headers=INTERNAL)
    llm = Llm(monkeypatch, ["Seul le second tourne."])

    run(client, dossier)

    steps = steps_of(client, dossier["id"])
    assert steps["Agent 1"]["output"] == "Déjà fait." and steps["Agent 2"]["output"] == "Seul le second tourne."
    assert len(llm.requests) == 1


def test_an_analysis_without_agent_still_gets_its_dossier_summary(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, _dispatched: dict
) -> None:
    dossier = launched_dossier(client, "Sans agent", agents=0)
    finish_upstream(client, dossier)
    llm = Llm(monkeypatch, [])

    run(client, dossier)

    assert llm.requests == [] and _dispatched["summary"] == [dossier["id"]]


def test_agents_interrupted_by_a_restart_are_failed_so_the_dossier_can_end(client: TestClient) -> None:
    dossier = launched_dossier(client, "Agent interrompu")
    finish_upstream(client, dossier)

    client.portal.call(agent_runner.fail_stale)

    agent = steps_of(client, dossier["id"])["Agent 1"]
    assert agent["status"] == "échec" and "interrompu" in agent["output"]
    assert client.get(f"/api/dossiers/{dossier['id']}").json()["status"] == "échec"


def test_the_ephemeral_pipeline_starts_the_agents_after_the_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.agent import dispatch

    chain: list[tuple] = []
    agents: list[tuple] = []
    monkeypatch.setattr(dispatch.celery_client, "dispatch_dossier_pipeline", lambda *args: chain.append(args))
    monkeypatch.setattr(dispatch, "dispatch_agent_execution", lambda *args: agents.append(args))

    dispatch.dispatch_dossier_pipeline(["d1", "d2"], "dossier-1")

    assert chain == [(["d1", "d2"], "dossier-1")] and agents == [("dossier-1",)]
