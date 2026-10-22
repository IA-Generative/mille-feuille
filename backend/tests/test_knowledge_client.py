import asyncio
import json

import httpx2
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.knowledge_sources import get_knowledge_client
from app.services.knowledge.client import HttpKnowledgeClient, KnowledgeError
from app.services.knowledge.contract import CollectionPage, LookupResult, SearchRequest, SearchResult
from tests.access_support import As
from tests.test_knowledge_sources import add
from tests.tool_support import FakeIdentityTokens

URL = "https://kb.example.gouv.fr"
HEADERS = {"Authorization": "Bearer t"}


def collection(id: str = "subv-guide") -> dict:
    return {"id": id, "name": "Guide des subventions", "description": "", "document_count": 85, "extension": "ignorée"}


def source(passage: str = "Un RIB est exigé.", **extra) -> dict:
    return {
        "id": "p-1",
        "kind": "document",
        "title": "Guide.pdf",
        "url": "https://kb.example.gouv.fr/doc/d-1?page=14",
        "preview_url": "https://kb.example.gouv.fr/doc/d-1/14.png",
        "page": 14,
        "boxes": [{"page": 14, "x_min": 0.1, "y_min": 0.2, "x_max": 0.9, "y_max": 0.3}],
        "passage": passage,
        "score": 0.91,
        "collection_id": "subv-guide",
    } | extra


def client_for(handler) -> HttpKnowledgeClient:
    return HttpKnowledgeClient(transport=httpx2.MockTransport(handler))


def run(coro):
    return asyncio.run(coro)


def test_the_collections_are_listed_with_server_side_pagination_and_filter() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"items": [collection()], "total": 12, "page": 2, "page_size": 5})

    page = run(client_for(handler).list_collections(URL, HEADERS, page=2, page_size=5, q="subvention"))

    assert isinstance(page, CollectionPage) and page.total == 12 and page.items[0].id == "subv-guide"
    assert not hasattr(page.items[0], "extension")  # un champ hors contrat n'est pas relayé
    assert str(seen[0].url) == f"{URL}/v1/collections?page=2&page_size=5&q=subvention"
    assert seen[0].headers["Authorization"] == "Bearer t"


def test_collections_are_looked_up_by_id_and_missing_ones_are_reported() -> None:
    bodies: list = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content))
        return httpx2.Response(200, json={"items": [collection()], "missing": [{"id": "crpa", "reason": "forbidden"}]})

    result = run(client_for(handler).lookup(URL, HEADERS, ["subv-guide", "crpa", "subv-guide"]))

    assert isinstance(result, LookupResult) and [m.reason for m in result.missing] == ["forbidden"]
    assert bodies == [{"ids": ["subv-guide", "crpa"]}]  # les doublons sont retirés
    with pytest.raises(KnowledgeError) as error:
        run(client_for(handler).lookup(URL, HEADERS, []))
    assert error.value.code == "invalid_request"


def test_a_search_keeps_the_results_of_the_collections_that_answer() -> None:
    sent: list = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "answer": "Un RIB est exigé.",
                "sources": [source()],
                "skipped": [{"collection_id": "circulaires", "reason": "unavailable"}],
                "usage": {"input_tokens": 18, "total_tokens": 18},
            },
        )

    request = SearchRequest(
        query="pièces à fournir", collection_ids=["subv-guide", "circulaires"], filters={"annee": 2020}
    )
    result = run(client_for(handler).search(URL, HEADERS, request))

    assert isinstance(result, SearchResult) and result.sources[0].page == 14 and result.answer == "Un RIB est exigé."
    assert [(s.collection_id, s.reason) for s in result.skipped] == [("circulaires", "unavailable")]
    assert result.usage.total_tokens == 18
    assert sent == [
        {
            "query": "pièces à fournir",
            "collection_ids": ["subv-guide", "circulaires"],
            "top_k": 5,
            "filters": {"annee": 2020},
            "max_chars": 4000,
        }
    ]


def test_the_text_of_a_passage_is_cut_to_the_size_asked() -> None:
    long = "x" * 1000

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"sources": [source(long), source("court")], "skipped": []})

    request = SearchRequest(query="pièces", collection_ids=["subv-guide"], max_chars=200)
    long_one, short_one = run(client_for(handler).search(URL, HEADERS, request)).sources

    assert len(long_one.passage) == 200 and long_one.truncated is True
    assert short_one.passage == "court" and short_one.truncated is False


def test_a_search_request_is_bounded_like_the_contract_before_any_call() -> None:
    for bad in (
        {"query": "ab", "collection_ids": ["a"]},
        {"query": "abc", "collection_ids": []},
        {"query": "abc", "collection_ids": [str(n) for n in range(21)]},
        {"query": "abc", "collection_ids": ["a"], "top_k": 51},
    ):
        with pytest.raises(ValueError):
            SearchRequest(**bad)


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx2.Response(401, json={"code": "unauthorized", "message": "Jeton invalide."}), "unauthorized"),
        (httpx2.Response(403), "forbidden"),
        (httpx2.Response(404, json={"code": "not_implemented", "message": "x"}), "not_implemented"),
        (httpx2.Response(422, json={"code": "no_usable_collection", "message": "x"}), "no_usable_collection"),
        (httpx2.Response(429, headers={"Retry-After": "3"}), "rate_limited"),
        (httpx2.Response(503), "unavailable"),
        (httpx2.Response(200, text="<html>"), "not_json"),
        (httpx2.Response(200, json={"sources": [{"id": "x"}], "skipped": []}), "invalid_response"),
        (httpx2.Response(200, json={"sources": [source(score=3)], "skipped": []}), "invalid_response"),
    ],
)
def test_errors_have_a_stable_code_and_a_fixed_message(response, code) -> None:
    request = SearchRequest(query="pièces", collection_ids=["subv-guide"])

    with pytest.raises(KnowledgeError) as error:
        run(client_for(lambda r: response).search(URL, HEADERS, request))

    assert error.value.code == code
    assert "Jeton invalide" not in error.value.message  # le message d'un tiers n'est pas relayé


def test_a_response_that_is_too_large_is_refused() -> None:
    big = {"sources": [source("x" * 5000) for _ in range(20)], "skipped": []}
    small_limit = HttpKnowledgeClient(
        transport=httpx2.MockTransport(lambda r: httpx2.Response(200, json=big)),
        settings=type("S", (), {"KNOWLEDGE_RESPONSE_MAX_BYTES": 1000, "TOOL_CALL_TIMEOUT_SECONDS": 5})(),
    )

    with pytest.raises(KnowledgeError) as error:
        run(small_limit.search(URL, HEADERS, SearchRequest(query="pièces", collection_ids=["a"])))

    assert error.value.code == "too_large"


def test_redirections_are_not_followed() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(302, headers={"Location": "http://169.254.169.254/"})

    with pytest.raises(KnowledgeError):
        run(client_for(handler).list_collections(URL, HEADERS, page=1, page_size=1, q=None))


def test_an_unreachable_provider_is_reported() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refusé")

    with pytest.raises(KnowledgeError) as error:
        run(client_for(handler).list_collections(URL, HEADERS, page=1, page_size=1, q=None))
    assert error.value.code == "unavailable"


# --- La route de liste des collections d'une source ---


class FakeClient:
    def __init__(self, result: CollectionPage | Exception) -> None:
        self.result = result
        self.calls: list[tuple] = []

    async def list_collections(self, url, headers, *, page, page_size, q):
        self.calls.append((url, headers, page, page_size, q))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def provider():
    fake = FakeClient(CollectionPage.model_validate({"items": [collection()], "total": 41, "page": 1, "page_size": 20}))
    app.dependency_overrides[get_knowledge_client] = lambda: fake
    yield fake
    del app.dependency_overrides[get_knowledge_client]


def test_the_collections_of_a_source_are_listed_with_the_identity_of_the_caller(
    client: TestClient, provider: FakeClient, identity_tokens: FakeIdentityTokens
) -> None:
    source = add(client, auth_mode="token_exchange", audience="kb-subventions").json()["id"]

    response = client.get(f"/api/knowledge-sources/{source}/collections", params={"q": "subv", "page": 2})

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["total"], body["pages"], body["items"][0]["id"]) == (41, 3, "subv-guide")
    assert provider.calls[-1] == (
        "https://kb.example.gouv.fr",
        {"Authorization": "Bearer exchanged-for-kb-subventions"},
        2,
        20,
        "subv",
    )


def test_the_collections_of_a_source_follow_the_visibility_of_the_source(
    client: TestClient, provider: FakeClient, world: dict
) -> None:
    with As(world["alice"]):
        private = add(client).json()["id"]
    provider.calls.clear()  # l'appel de vérification fait à l'ajout
    with As(world["bob"]):
        assert client.get(f"/api/knowledge-sources/{private}/collections").status_code == 404
    assert provider.calls == []


@pytest.mark.parametrize(("code", "status"), [("rate_limited", 429), ("invalid_request", 422), ("unavailable", 502)])
def test_provider_errors_become_stable_responses(
    client: TestClient, provider: FakeClient, code: str, status: int
) -> None:
    source = add(client).json()["id"]
    provider.result = KnowledgeError(code)

    response = client.get(f"/api/knowledge-sources/{source}/collections")

    assert response.status_code == status and response.json()["detail"]["code"] == code


# --- La forme normalisée d'une réponse (#369) ---


def search_with(body: dict) -> SearchResult:
    request = SearchRequest(query="pièces", collection_ids=["subv-guide"])
    return run(client_for(lambda r: httpx2.Response(200, json=body)).search(URL, HEADERS, request))


def test_a_web_source_has_a_link_and_no_page_no_preview_no_boxes() -> None:
    web = source(id="w-1", kind="web", title="Service-Public", url="https://www.service-public.example.fr/x", page=None)
    web |= {"preview_url": None, "boxes": []}

    result = search_with({"answer": None, "sources": [web], "skipped": []})

    assert result.answer is None
    [found] = result.sources
    assert (found.kind, found.page, found.preview_url, found.boxes) == ("web", None, None, [])


def test_a_response_without_boxes_or_preview_keys_is_still_valid() -> None:
    bare = {k: v for k, v in source().items() if k not in ("preview_url", "boxes", "page")}

    [found] = search_with({"sources": [bare]}).sources

    assert (found.boxes, found.preview_url, found.page) == ([], None, None)


@pytest.mark.parametrize(
    "bad",
    [
        {"url": "javascript:alert(1)"},
        {"url": "ftp://kb.example.gouv.fr/doc"},
        {"url": ""},
        {"boxes": [{"page": 1, "x_min": 0.1, "y_min": 0.1, "x_max": 1.5, "y_max": 0.3}]},  # hors de 0..1
        {"boxes": [{"page": 1, "x_min": 0.9, "y_min": 0.1, "x_max": 0.1, "y_max": 0.3}]},  # pas un rectangle
        {"boxes": [{"page": 0, "x_min": 0.1, "y_min": 0.1, "x_max": 0.2, "y_max": 0.3}]},
        {"kind": "pdf"},
    ],
)
def test_a_source_that_breaks_the_contract_invalidates_the_response(bad: dict) -> None:
    with pytest.raises(KnowledgeError) as error:
        search_with({"sources": [source(**bad)]})
    assert error.value.code == "invalid_response"


def test_a_preview_that_is_not_http_is_ignored_without_invalidating_the_response() -> None:
    [found] = search_with({"sources": [source(preview_url="data:image/png;base64,AAAA")]}).sources

    assert found.preview_url is None and found.url.startswith("https://")


def test_the_answer_of_the_provider_is_bounded() -> None:
    result = search_with({"answer": "a" * 9000, "sources": [], "skipped": []})

    assert len(result.answer) == 4000 and result.answer_truncated is True


def test_a_collection_may_have_a_link_and_a_thumbnail_that_are_checked() -> None:
    page = run(
        client_for(
            lambda r: httpx2.Response(
                200,
                json={
                    "items": [
                        collection() | {"url": "https://kb.example.gouv.fr/c/guide", "preview_url": "javascript:x"},
                        collection("autre"),
                    ],
                    "total": 2,
                    "page": 1,
                    "page_size": 20,
                },
            )
        ).list_collections(URL, HEADERS, page=1, page_size=20, q=None)
    )

    first, second = page.items
    assert (first.url, first.preview_url) == ("https://kb.example.gouv.fr/c/guide", None)
    assert (second.url, second.preview_url) == (None, None)
