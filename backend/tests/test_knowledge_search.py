import uuid

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import async_session_factory
from app.main import app
from app.models.tool import ToolCallLog
from app.routers.internal_tools import get_call_limiter
from app.routers.knowledge_sources import get_knowledge_client
from app.services.knowledge.client import KnowledgeError
from app.services.knowledge.contract import Passage, SearchRequest, SearchResult, SkippedCollection
from app.services.tools.call_limits import CallLimiter
from tests.access_support import As
from tests.test_analysis_knowledge import FakeProvider, make_analyse, make_source, put
from tests.test_knowledge_sources import probe as probe  # noqa: F401  (fixture : vérification de connexion simulée)
from tests.tool_support import FakeIdentityTokens

TOKEN = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


def passage(collection: str, score: float, text: str = "Un RIB est exigé.", **extra) -> Passage:
    return Passage(
        passage_id=f"p-{collection}-{score}",
        collection_id=collection,
        document_id="d-1",
        document_name="Guide.pdf",
        page=14,
        text=text,
        score=score,
        source_url="https://kb.example.gouv.fr/doc",
    ).model_copy(update=extra)


class SearchProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self.passages: dict[str, list[Passage]] = {}
        self.search_errors: dict[str, KnowledgeError] = {}
        self.searches: list[tuple[str, dict, SearchRequest]] = []

    async def search(self, url, headers, request: SearchRequest) -> SearchResult:
        self.searches.append((url, headers, request))
        for collection in request.collection_ids:
            if collection in self.search_errors:
                raise self.search_errors[collection]
        items = [p for c in request.collection_ids for p in self.passages.get(c, [])]
        skipped = [
            SkippedCollection(collection_id=c, reason="unavailable")
            for c in request.collection_ids
            if c in self.forbidden
        ]
        return SearchResult(items=[p for p in items if p.collection_id not in self.forbidden], skipped=skipped)


@pytest.fixture
def provider():
    fake = SearchProvider()
    fake.passages = {
        "guide": [passage("guide", 0.91), passage("guide", 0.40)],
        "circulaires": [passage("circulaires", 0.75)],
    }
    app.dependency_overrides[get_knowledge_client] = lambda: fake
    yield fake
    del app.dependency_overrides[get_knowledge_client]


def search(client: TestClient, analyse: str, *, person=None, query: str = "pièces à fournir", **extra):
    headers = {**TOKEN, **({"X-Acting-User": person.user_id} if person else {})}
    body = {"analyse_id": analyse, "query": query, "run_id": f"run-{uuid.uuid4().hex[:8]}"} | extra
    return client.post("/api/internal/knowledge/search", json=body, headers=headers)


def logs_of(client: TestClient, user_id: str) -> list[ToolCallLog]:
    async def read() -> list[ToolCallLog]:
        async with async_session_factory() as session:
            return list(
                (
                    await session.execute(
                        select(ToolCallLog).where(ToolCallLog.user_id == user_id).order_by(ToolCallLog.created_at)
                    )
                ).scalars()
            )

    return client.portal.call(read)


def chosen(client: TestClient, provider, *collections: str, **source_extra) -> tuple[str, str]:
    analyse, source = make_analyse(client), make_source(client, **({"visibility": "all"} | source_extra))
    assert put(client, analyse, *[(source, c) for c in collections]).status_code == 200
    return analyse, source


def test_passages_are_merged_ranked_and_cited(client: TestClient, provider, probe) -> None:
    analyse, _ = chosen(client, provider, "guide", "circulaires")

    body = search(client, analyse, top_k=2).json()

    assert body["ok"] is True and body["untrusted"] is True
    assert [(p["collection_id"], p["score"]) for p in body["passages"]] == [("guide", 0.91), ("circulaires", 0.75)]
    first = body["passages"][0]
    assert (first["document_name"], first["page"], first["collection_name"]) == (
        "Guide.pdf",
        14,
        "Guide des subventions",
    )
    assert first["source_url"] == "https://kb.example.gouv.fr/doc" and first["source_name"].startswith("Références")
    sent = provider.searches[0][2]
    assert (sent.query, sent.top_k, sent.max_chars) == ("pièces à fournir", 2, 1500)


def test_the_search_is_made_with_the_identity_of_the_person(
    client: TestClient, provider, probe, identity_tokens: FakeIdentityTokens, world: dict
) -> None:
    with As(world["alice"]):
        analyse, _ = chosen(client, provider, "guide", auth_mode="token_exchange", audience="kb-subventions")
    identity_tokens.calls.clear()

    body = search(client, analyse, person=world["bob"]).json()

    assert body["ok"] is True
    assert provider.searches[-1][1] == {"Authorization": "Bearer exchanged-for-kb-subventions"}
    assert identity_tokens.calls == [(world["bob"].user_id, "kb-subventions")]


def test_without_a_person_the_search_fails_with_a_stable_code(
    client: TestClient, provider, probe, identity_tokens: FakeIdentityTokens
) -> None:
    analyse, _ = chosen(client, provider, "guide", auth_mode="token_exchange", audience="kb-subventions")
    searches = len(provider.searches)

    body = search(client, analyse).json()

    assert (body["ok"], body["code"]) == (False, "identite_absente")
    assert len(provider.searches) == searches  # le fournisseur n'a pas été appelé


def test_a_collection_that_fails_does_not_stop_the_others(client: TestClient, provider, probe) -> None:
    analyse, _ = chosen(client, provider, "guide", "circulaires")
    provider.forbidden = {"circulaires"}

    body = search(client, analyse).json()

    assert body["ok"] is True and {p["collection_id"] for p in body["passages"]} == {"guide"}
    assert [(s["collection_id"], s["collection_name"]) for s in body["skipped"]] == [("circulaires", "Circulaires")]


def test_a_provider_that_fails_is_skipped_and_when_nothing_answers_the_code_says_so(
    client: TestClient, provider, probe
) -> None:
    analyse, _ = chosen(client, provider, "guide", "circulaires")
    provider.search_errors = {"guide": KnowledgeError("unavailable")}

    body = search(client, analyse).json()

    assert (body["ok"], body["code"]) == (False, "aucune_collection_disponible")
    assert {s["collection_id"] for s in body["skipped"]} == {"guide", "circulaires"}


def test_an_analyse_without_collections_says_so(client: TestClient, provider) -> None:
    body = search(client, make_analyse(client)).json()

    assert (body["ok"], body["code"]) == (False, "aucune_collection")
    assert provider.searches == []


def test_a_source_the_person_cannot_see_is_skipped(client: TestClient, provider, probe, world: dict) -> None:
    with As(world["alice"]):
        analyse, _ = chosen(client, provider, "guide", visibility="private")
    searches = len(provider.searches)

    with As(world["bob"]):
        body = search(client, analyse, person=world["bob"]).json()

    assert (body["ok"], body["code"]) == (False, "aucune_collection_disponible")
    assert len(provider.searches) == searches


def test_the_output_is_bounded_and_links_are_http_only(
    client: TestClient, provider, probe, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TOOL_OUTPUT_MAX_CHARS", "4000")
    analyse, _ = chosen(client, provider, "guide")
    provider.passages["guide"] = [
        passage("guide", 0.9, "x" * 1500, source_url="javascript:alert(1)"),
        *[passage("guide", 0.5 - i / 100, "y" * 1500) for i in range(14)],
    ]

    body = search(client, analyse, top_k=10).json()

    assert body["truncated"] is True and len(body["passages"]) == 2  # les mieux classés tiennent dans 4 000 caractères
    assert sum(len(p["text"]) for p in body["passages"]) <= 4000
    assert body["passages"][0]["source_url"] is None


def test_each_source_consulted_is_logged_without_the_question(client: TestClient, provider, probe, world: dict) -> None:
    analyse, _ = chosen(client, provider, "guide")

    search(client, analyse, person=world["bob"], query="un secret médical")

    [log] = logs_of(client, world["bob"].user_id)
    assert (log.tool_name, log.outcome, log.server_id) == ("base_connaissances", "ok", None)
    assert log.server_name.startswith("Références")
    assert "secret" not in repr(vars(log))


def test_the_quota_stops_the_searches(client: TestClient, provider, probe, world: dict) -> None:
    analyse, _ = chosen(client, provider, "guide")
    limiter = CallLimiter(fakeredis.FakeRedis(decode_responses=True), per_run=2, per_minute=100)
    app.dependency_overrides[get_call_limiter] = lambda: limiter
    try:
        codes = [search(client, analyse, person=world["bob"], run_id="r1").json().get("code") for _ in range(3)]
    finally:
        del app.dependency_overrides[get_call_limiter]

    assert codes == [None, None, "quota_depasse"]


def test_the_route_needs_the_worker_token_and_a_valid_request(client: TestClient, provider) -> None:
    analyse = make_analyse(client)
    body = {"analyse_id": analyse, "query": "pièces"}

    assert client.post("/api/internal/knowledge/search", json=body).status_code == 422  # en-tête absent
    bad = {"X-App-Token": "nope"}
    assert client.post("/api/internal/knowledge/search", json=body, headers=bad).status_code == 401
    assert search(client, analyse, query="ab").status_code == 422
    assert search(client, analyse, top_k=11).status_code == 422
    assert search(client, str(uuid.uuid4())).status_code == 404
