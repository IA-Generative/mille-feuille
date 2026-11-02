"""Le chat d'un dossier, de bout en bout dans le backend : le LLM, la recherche et Qdrant sont simulés ; la base et
Redis sont réels. Un message déclenche un plan, une recherche et une réponse écrite en streaming — ou, selon le plan, la
boucle d'outils.

Les travaux tournent sur la boucle de l'application (`client.portal`), celle qui possède le moteur de base."""

import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agent import usage
from app.agent.chat import answer as answer_module
from app.agent.chat import job
from app.agent.chat.job import run_chat
from app.agent.tools import NotIndexedError, SearchHit
from app.db import async_session_factory
from app.repositories.dossier_repository import DossierRepository
from app.services import chat_stream
from tests.test_conversation_tools import analyse_with_tools, open_chat

CONTENT = "Le loyer mensuel est de 800 euros, charges comprises."


@pytest.fixture(autouse=True)
def _no_dispatch_no_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    # Le message de la personne ne lance pas le travail tout seul : le test le lance, sur la boucle de l'application.
    monkeypatch.setattr("app.routers.dossiers.dispatch_chat_response", lambda *args: None)

    async def no_usage(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(usage, "record", no_usage)


class Llm:
    """Le modèle, simulé : `complete` rend les réponses dans l'ordre (le plan d'abord), `client()` écrit la réponse en
    streaming. Tout ce qui lui a été demandé est gardé."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, completions: list, streamed: list[str] | None = None):
        self.completions = list(completions)
        self.streamed = streamed or []
        self.requests: list[dict] = []
        self.stream_requests: list[dict] = []
        llm = self

        async def complete(**kwargs: object) -> SimpleNamespace:
            llm.requests.append(kwargs)
            item = llm.completions.pop(0)
            if isinstance(item, Exception):
                raise item
            message = SimpleNamespace(content=item if isinstance(item, str) else None, tool_calls=None)
            if isinstance(item, tuple):
                name, arguments = item
                call = SimpleNamespace(
                    id="call-1", function=SimpleNamespace(name=name, arguments=json.dumps(arguments))
                )
                message = SimpleNamespace(content="", tool_calls=[call])
            return SimpleNamespace(model="m", usage=None, choices=[SimpleNamespace(message=message)])

        class Completions:
            async def create(self, **kwargs: object):  # noqa: ANN202
                llm.stream_requests.append(kwargs)
                if isinstance(llm.streamed, Exception):
                    raise llm.streamed

                async def chunks():  # noqa: ANN202
                    for piece in llm.streamed:
                        delta = SimpleNamespace(content=piece)
                        yield SimpleNamespace(model="m", usage=None, choices=[SimpleNamespace(delta=delta)])
                    yield SimpleNamespace(model="m", usage=SimpleNamespace(), choices=[])

                return chunks()

        monkeypatch.setattr(job.react.llm, "complete", complete)
        monkeypatch.setattr("app.agent.chat.planner.llm.complete", complete)
        monkeypatch.setattr(
            answer_module.llm, "client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
        )


def plan(**fields: object) -> str:
    return json.dumps(fields)


class Searcher:
    def __init__(self, hits: list[SearchHit] | Exception) -> None:
        self.hits = hits
        self.queries: list[str] = []

    async def search(self, query: str) -> list[SearchHit]:
        self.queries.append(query)
        if isinstance(self.hits, Exception):
            raise self.hits
        return self.hits


def use_searcher(monkeypatch: pytest.MonkeyPatch, searcher: Searcher) -> None:
    monkeypatch.setattr(job, "DossierSearcher", lambda dossier_id: searcher)


def setup_chat(client: TestClient, text: str = CONTENT) -> dict:
    """Un dossier avec un document d'une page, et une conversation où la personne vient de poser sa question."""
    dossier_id, conversation_id = open_chat(client, analyse_with_tools(client, ["calculatrice"]))
    client.post(
        f"/api/dossiers/{dossier_id}/documents", files=[("files", ("bail.pdf", b"fake-bytes", "application/pdf"))]
    )
    document = client.get(f"/api/dossiers/{dossier_id}").json()["documents"][0]
    page = client.post(
        f"/api/internal/documents/{document['id']}/pages",
        json={"page_number": 1, "content": text},
        headers={"X-App-Token": "dev-only-worker-token-not-for-prod"},
    ).json()
    client.post(
        f"/api/dossiers/{dossier_id}/conversations/{conversation_id}/messages", json={"content": "Quel est le loyer ?"}
    )
    return {"dossier": dossier_id, "conversation": conversation_id, "document": document["id"], "page": page["id"]}


def hit(ids: dict, excerpt: str = CONTENT) -> SearchHit:
    return SearchHit(ids["page"], 1, ids["document"], "bail.pdf", 0.9, excerpt)


def run(client: TestClient, ids: dict) -> None:
    client.portal.call(run_chat, ids["conversation"], ids["dossier"])


def messages(client: TestClient, ids: dict) -> list[dict]:
    url = f"/api/dossiers/{ids['dossier']}/conversations/{ids['conversation']}/messages"
    return client.get(url).json()["items"]


def events(client: TestClient, ids: dict) -> list[tuple[str, dict]]:
    async def read() -> list[tuple[str, dict]]:
        async with async_session_factory() as db:
            rows = await DossierRepository(db).list_chat_events(uuid.UUID(ids["conversation"]), after_id=None)
            return [(row.kind.value, row.data) for row in rows]

    return client.portal.call(read)


def deltas(client: TestClient, ids: dict) -> str:
    return "".join(text for _id, text in client.portal.call(chat_stream.read, ids["conversation"], "0", 50))


def test_a_question_costs_a_plan_a_search_and_a_streamed_answer(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = setup_chat(client)
    searcher = Searcher([hit(ids)])
    use_searcher(monkeypatch, searcher)
    llm = Llm(
        monkeypatch,
        completions=[plan(mode="search", standalone_query="montant du loyer", queries=["loyer mensuel"])],
        streamed=["Le loyer est de ", "800 euros [1]."],
    )

    run(client, ids)

    # Deux appels au modèle : le plan, puis la réponse (pas de boucle d'outils).
    assert len(llm.requests) == 1 and len(llm.stream_requests) == 1
    assert "loyer mensuel" in searcher.queries and "Quel est le loyer ?" in searcher.queries
    system = llm.stream_requests[0]["messages"][0]["content"]
    assert "[1] 📄 Page 1 (bail.pdf)" in system and CONTENT in system
    assert llm.stream_requests[0]["stream"] is True
    [*_, reply] = messages(client, ids)
    assert reply["role"] == "assistant" and reply["content"] == "Le loyer est de 800 euros [1]."
    assert [(s["number"], s["excerpt"]) for s in reply["sources"]] == [(1, CONTENT)]
    kinds = [kind for kind, _ in events(client, ids)]
    assert kinds == ["tool_call", "tool_result", "done"]
    assert deltas(client, ids) == "Le loyer est de 800 euros [1]."


def test_a_greeting_is_answered_by_the_plan_alone(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = setup_chat(client)
    searcher = Searcher([hit(ids)])
    use_searcher(monkeypatch, searcher)
    llm = Llm(monkeypatch, completions=[plan(mode="direct", answer="Bonjour ! Je peux vous aider sur ce dossier.")])

    run(client, ids)

    assert len(llm.requests) == 1 and llm.stream_requests == []
    assert messages(client, ids)[-1]["content"] == "Bonjour ! Je peux vous aider sur ce dossier."
    assert [kind for kind, _ in events(client, ids)] == ["done"]


def test_a_search_without_result_falls_back_on_the_tools(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = setup_chat(client)
    use_searcher(monkeypatch, Searcher([]))
    llm = Llm(
        monkeypatch,
        completions=[plan(mode="search", queries=["loyer"]), ("read_page", {"page_number": 1}), "Il est de 800 €."],
    )

    run(client, ids)

    assert llm.stream_requests == []
    assert messages(client, ids)[-1]["content"] == "Il est de 800 €."
    tool_events = [(kind, data.get("tool_name")) for kind, data in events(client, ids)]
    assert ("tool_call", "read_page") in tool_events and tool_events[-1][0] == "done"


def test_a_dossier_that_is_not_indexed_falls_back_on_the_tools(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = setup_chat(client)
    use_searcher(monkeypatch, Searcher(NotIndexedError("non indexé")))
    Llm(monkeypatch, completions=[plan(mode="search", queries=["loyer"]), "Réponse lue dans les pages."])

    run(client, ids)

    assert messages(client, ids)[-1]["content"] == "Réponse lue dans les pages."


def test_a_plan_that_fails_still_searches_the_question(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = setup_chat(client)
    searcher = Searcher([hit(ids)])
    use_searcher(monkeypatch, searcher)
    Llm(monkeypatch, completions=[RuntimeError("hub LLM indisponible")], streamed=["800 euros."])

    run(client, ids)

    assert searcher.queries == ["Quel est le loyer ?", "Quel est le loyer ?"][: len(searcher.queries)]
    assert messages(client, ids)[-1]["content"] == "800 euros."


def test_a_question_to_the_person_is_stored_for_their_answer(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = setup_chat(client)
    use_searcher(monkeypatch, Searcher([]))
    question = {
        "question": "De quel bail parlez-vous ?",
        "header": "Bail",
        "options": [{"label": "Bail 2023", "description": "Le premier"}, {"label": "Bail 2024"}],
    }
    Llm(monkeypatch, completions=[plan(mode="clarify", questions=[question])])

    run(client, ids)

    [call] = messages(client, ids)[-1]["tool_calls"]
    assert call["tool_id"] == "ask_user" and call["status"] == "pending"
    assert call["arguments"]["questions"][0]["question"] == "De quel bail parlez-vous ?"


def test_a_request_about_the_application_offers_its_assistant(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = setup_chat(client)
    use_searcher(monkeypatch, Searcher([]))
    Llm(
        monkeypatch,
        completions=[plan(mode="assistant", answer="L'assistant s'en charge.", standalone_query="Crée une analyse")],
    )

    run(client, ids)

    content = messages(client, ids)[-1]["content"]
    assert content.startswith("L'assistant s'en charge.") and "<!--assistant-suggestion:" in content


def test_a_failing_model_ends_the_stream_with_an_error(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = setup_chat(client)
    use_searcher(monkeypatch, Searcher([hit(ids)]))
    llm = Llm(monkeypatch, completions=[plan(mode="search", queries=["loyer"])])
    llm.streamed = RuntimeError("hub LLM indisponible")  # type: ignore[assignment]

    run(client, ids)

    kinds = [kind for kind, _ in events(client, ids)]
    assert kinds[-1] == "error" and "done" not in kinds
    assert events(client, ids)[-1][1]["message"] == "hub LLM indisponible"
    assert messages(client, ids)[-1]["role"] == "user"  # pas de réponse à moitié écrite


def test_the_sse_stream_carries_the_answer_as_it_is_written(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = setup_chat(client)
    use_searcher(monkeypatch, Searcher([hit(ids)]))
    Llm(monkeypatch, completions=[plan(mode="search", queries=["loyer"])], streamed=["800 ", "euros."])

    run(client, ids)

    with client.stream("GET", f"/api/dossiers/{ids['dossier']}/conversations/{ids['conversation']}/stream") as response:
        body = "".join(response.iter_text())
    received = [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ") and line != "data: {}"
    ]
    assert "".join(e["data"]["text"] for e in received if e["kind"] == "delta") == "800 euros."
    assert [e["kind"] for e in received if e["kind"] != "delta"] == ["tool_call", "tool_result", "done"]
