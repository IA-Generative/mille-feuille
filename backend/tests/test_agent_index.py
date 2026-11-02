"""L'index des agents d'une analyse : la question retrouve l'agent dont le rôle correspond. Qdrant tourne en
mémoire, les embeddings sont simulés (un vecteur par thème) ; le lexical (BM25) est le vrai."""

import uuid

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.agent.analysis_agents import AnalysisAgent
from app.agent.chat import agent_reply
from app.agent.jobs.agent_index import index_analyse_agents
from app.services.search import agent_index as index
from app.services.search import qdrant_store as store
from app.services.search.agent_index import IndexedAgent

THEMES = ("juridique", "montant", "calendrier")


def vector_of(text: str) -> list[float]:
    lowered = text.lower()
    vector = [1.0 if theme in lowered else 0.0 for theme in THEMES]
    return vector if any(vector) else [0.1, 0.1, 0.1]


@pytest.fixture
def embedded(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Qdrant en mémoire, des embeddings par thème ; renvoie les lots de textes qui ont été embeddés."""
    memory = QdrantClient(":memory:")
    monkeypatch.setattr(store, "get_client", lambda: memory)
    monkeypatch.setenv("QDRANT_URL", "http://qdrant.test")
    monkeypatch.setenv("SEARCH_EMBEDDING_MODEL", "fake-embed")
    batches: list[list[str]] = []

    def embed_dense(texts: list[str], model: str) -> list[list[float]]:
        batches.append(texts)
        return [vector_of(text) for text in texts]

    async def embed_query(text: str, model: str) -> list[float]:
        return vector_of(text)

    monkeypatch.setattr(index, "embed_dense", embed_dense)
    monkeypatch.setattr(index, "embed_query", embed_query)
    return batches


def agents() -> list[IndexedAgent]:
    return [
        IndexedAgent("a1", "Juriste", "Tu analyses les clauses juridiques et les obligations du contrat."),
        IndexedAgent("a2", "Comptable", "Tu vérifies chaque montant, les charges et les totaux."),
        IndexedAgent("a3", "Planificateur", "Tu construis le calendrier des échéances et des délais."),
    ]


@pytest.mark.anyio
async def test_a_question_finds_the_agent_whose_role_matches(embedded: list) -> None:
    index.sync_analyse("an1", agents(), "fake-embed")

    assert (await index.find("an1", "Quel est le montant des charges ?", "fake-embed", 2))[0] == "a2"
    assert (await index.find("an1", "Quelles sont les obligations juridiques ?", "fake-embed", 2))[0] == "a1"


@pytest.mark.anyio
async def test_the_lexical_branch_finds_an_agent_the_embedding_cannot_tell_apart(embedded: list) -> None:
    index.sync_analyse("an1", agents(), "fake-embed")

    # « délais » ne dit rien au faux embedding (vecteur neutre) : seul le BM25 retrouve le planificateur.
    assert (await index.find("an1", "délais", "fake-embed", 1)) == ["a3"]


@pytest.mark.anyio
async def test_only_what_changed_is_embedded_again_and_removed_agents_leave_the_index(embedded: list) -> None:
    assert index.sync_analyse("an1", agents(), "fake-embed") == {"indexed": 3, "removed": 0}
    assert index.sync_analyse("an1", agents(), "fake-embed") == {"indexed": 0, "removed": 0}

    changed = [IndexedAgent("a1", "Juriste", "Tu relis les baux commerciaux."), *agents()[1:2]]
    assert index.sync_analyse("an1", changed, "fake-embed") == {"indexed": 1, "removed": 1}
    assert embedded[-1] == ["Juriste\nTu relis les baux commerciaux."]
    assert sorted(await index.find("an1", "baux montant", "fake-embed", 5)) == ["a1", "a2"]


@pytest.mark.anyio
async def test_agents_of_another_analysis_are_never_found(embedded: list) -> None:
    index.sync_analyse("an1", agents()[:1], "fake-embed")
    index.sync_analyse("an2", agents()[1:2], "fake-embed")

    assert await index.find("an1", "montant charges juridique", "fake-embed", 5) == ["a1"]
    assert await index.find("an2", "montant charges juridique", "fake-embed", 5) == ["a2"]


@pytest.mark.anyio
async def test_an_analysis_never_indexed_finds_nothing(embedded: list) -> None:
    assert await index.find("an-vide", "montant", "fake-embed", 3) == []


def team(count: int) -> list[AnalysisAgent]:
    return [
        AnalysisAgent(str(rank), f"Agent {rank}", f"Prompt {rank}", [], None, f"id{rank}")
        for rank in range(1, count + 1)
    ]


def test_few_agents_are_all_given_to_the_plan(client: TestClient, embedded: list) -> None:
    given = team(3)
    assert client.portal.call(agent_reply.shortlist, str(uuid.uuid4()), "question", given) == given
    assert embedded == []  # aucun appel au modèle d'embeddings


def test_many_agents_are_narrowed_to_the_closest_ones_keeping_their_rank(
    client: TestClient, embedded: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def find(analyse_id: str, question: str, model: str, limit: int) -> list[str]:
        assert (model, limit) == ("fake-embed", agent_reply.SHORTLIST)
        return ["id7", "id2"]

    monkeypatch.setattr(index, "find", find)

    shortlisted = client.portal.call(agent_reply.shortlist, str(uuid.uuid4()), "question", team(8))

    assert [(a.ref, a.id) for a in shortlisted] == [("7", "id7"), ("2", "id2")]


def test_a_failing_or_empty_search_gives_all_the_agents(
    client: TestClient, embedded: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    everyone = team(8)

    async def broken(*args: object) -> list[str]:
        raise RuntimeError("Qdrant injoignable")

    monkeypatch.setattr(index, "find", broken)
    assert client.portal.call(agent_reply.shortlist, str(uuid.uuid4()), "question", everyone) == everyone

    async def nothing(*args: object) -> list[str]:
        return []

    monkeypatch.setattr(index, "find", nothing)
    assert client.portal.call(agent_reply.shortlist, str(uuid.uuid4()), "question", everyone) == everyone
    assert client.portal.call(agent_reply.shortlist, str(uuid.uuid4()), "  ", everyone) == everyone


def test_without_qdrant_all_the_agents_are_given(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDRANT_URL", "")
    everyone = team(8)
    assert client.portal.call(agent_reply.shortlist, str(uuid.uuid4()), "question", everyone) == everyone
    client.portal.call(index_analyse_agents, str(uuid.uuid4()))  # sans effet, sans erreur


def test_creating_an_agent_and_changing_its_prompt_refreshes_the_index(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatched: list[str] = []
    monkeypatch.setattr("app.agent.dispatch.dispatch_index_agents", dispatched.append)
    analyse = client.post("/api/analyses", json={"name": f"Index {uuid.uuid4().hex[:6]}", "description": "T"}).json()

    created = client.post(
        f"/api/analyses/{analyse['id']}/agents", json={"name": "Juriste", "prompt": "A", "tools": [], "output": True}
    ).json()
    client.put(f"/api/analyses/{analyse['id']}/agents/{created['id']}/prompt", json={"prompt": "B"})
    client.put(f"/api/analyses/{analyse['id']}/agents/{created['id']}/prompt", json={"prompt": "B"})  # inchangé

    assert dispatched == [analyse["id"], analyse["id"]]


def test_the_job_indexes_the_agents_of_an_analysis(
    client: TestClient, embedded: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.agent.dispatch.dispatch_index_agents", lambda analyse_id: None)
    analyse = client.post("/api/analyses", json={"name": f"Index {uuid.uuid4().hex[:6]}", "description": "T"}).json()
    for name, prompt in (("Juriste", "Clauses juridiques."), ("Comptable", "Montants et charges.")):
        client.post(
            f"/api/analyses/{analyse['id']}/agents", json={"name": name, "prompt": prompt, "tools": [], "output": True}
        )

    client.portal.call(index_analyse_agents, analyse["id"])

    assert sorted(len(batch) for batch in embedded) == [2]
    found = client.portal.call(index.find, analyse["id"], "montant", "fake-embed", 1)
    assert len(found) == 1
