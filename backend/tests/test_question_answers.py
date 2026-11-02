"""Les réponses prêtes aux questions fréquentes d'un dossier : calculées à la fin de l'analyse, le LLM et la recherche
sont simulés, la base est réelle. Les travaux tournent sur la boucle de l'application (`client.portal`)."""

import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.agent import dispatch, usage
from app.agent.jobs import agents as agents_job
from app.agent.jobs import question_answers as job
from app.agent.jobs.question_answers import answer_questions
from app.agent.tools import SearchHit
from app.db import async_session_factory
from app.models.document_page import DocumentPage
from app.models.question_answer import DossierQuestionAnswer, QuestionAnswerStatus
from tests.access_support import As
from tests.test_analysis_proposals import _setup as setup_analysis
from tests.test_dossier_access import _create

INTERNAL = {"X-App-Token": "dev-only-worker-token-not-for-prod"}
RENT = "Le loyer mensuel est de 800 euros, charges comprises."


@pytest.fixture(autouse=True)
def _quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_usage(*args: object, **kwargs: object) -> None:
        return None

    async def index_ready(dossier_id: uuid.UUID) -> bool:
        return True

    monkeypatch.setattr(usage, "record", no_usage)
    monkeypatch.setattr(job, "_index_ready", index_ready)
    monkeypatch.setattr(job, "DEBOUNCE", 0)


class Llm:
    """Le modèle : répond à chaque demande selon la question (la dernière parole de la personne)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, answers: dict[str, object]) -> None:
        self.answers = answers
        self.questions: list[str] = []
        llm = self

        async def complete(**kwargs: object) -> SimpleNamespace:
            question = kwargs["messages"][-1]["content"]
            llm.questions.append(question)
            outcome = llm.answers[question]
            if isinstance(outcome, Exception):
                raise outcome
            message = SimpleNamespace(content=json.dumps(outcome), tool_calls=None)
            return SimpleNamespace(model="m", usage=None, choices=[SimpleNamespace(message=message)])

        monkeypatch.setattr(job.llm, "complete", complete)


class Searcher:
    def __init__(self, ids: dict, found: bool = True) -> None:
        self.ids, self.found = ids, found
        self.queries: list[str] = []

    async def search(self, query: str) -> list[SearchHit]:
        self.queries.append(query)
        if not self.found:
            return []
        return [SearchHit(self.ids["page"], 1, self.ids["document"], "bail.pdf", 0.9, RENT)]


def setup_dossier(client: TestClient, questions: list[str]) -> dict:
    analyse = client.post("/api/analyses", json={"name": f"Q {uuid.uuid4().hex[:6]}", "description": "Baux"}).json()
    client.put(f"/api/analyses/{analyse['id']}/frequent-questions", json={"questions": questions})
    dossier = _create(client, analyse, visibility="analyse")
    client.post(
        f"/api/dossiers/{dossier['id']}/documents", files=[("files", ("bail.pdf", b"fake-bytes", "application/pdf"))]
    )
    document = client.get(f"/api/dossiers/{dossier['id']}").json()["documents"][0]
    page = client.post(
        f"/api/internal/documents/{document['id']}/pages",
        json={"page_number": 1, "content": RENT},
        headers=INTERNAL,
    ).json()
    return {"analyse": analyse["id"], "dossier": dossier["id"], "document": document["id"], "page": page["id"]}


def use_searcher(monkeypatch: pytest.MonkeyPatch, searcher: Searcher) -> None:
    monkeypatch.setattr(job, "DossierSearcher", lambda dossier_id: searcher)


def run(client: TestClient, ids: dict, full: bool = True) -> None:
    client.portal.call(answer_questions, ids["dossier"], full)


def answers(client: TestClient, ids: dict) -> dict:
    return client.get(f"/api/dossiers/{ids['dossier']}/question-answers").json()


def rows(client: TestClient, ids: dict) -> list[DossierQuestionAnswer]:
    async def read() -> list[DossierQuestionAnswer]:
        async with async_session_factory() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(DossierQuestionAnswer)
                .where(DossierQuestionAnswer.dossier_id == uuid.UUID(ids["dossier"]))
                .order_by(DossierQuestionAnswer.position)
            )
            return list(result.scalars().all())

    return client.portal.call(read)


ANSWER = {"answerable": True, "answer": "Le loyer est de **800 euros** [1]."}
NONE = {"answerable": False, "answer": ""}


def test_each_question_gets_its_answer_with_its_sources_in_the_order_of_the_analysis(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = setup_dossier(client, ["Quel est le loyer ?", "Qui est le bailleur ?"])
    use_searcher(monkeypatch, Searcher(ids))
    Llm(
        monkeypatch,
        {"Quel est le loyer ?": ANSWER, "Qui est le bailleur ?": {"answerable": True, "answer": "M. Durand [1]."}},
    )

    run(client, ids)

    body = answers(client, ids)
    assert body["status"] == "ready"
    assert [a["question"] for a in body["answers"]] == ["Quel est le loyer ?", "Qui est le bailleur ?"]
    first = body["answers"][0]
    assert first["answer"] == "Le loyer est de **800 euros** [1]."
    assert first["sources"][0]["number"] == 1 and first["sources"][0]["page_ids"] == [ids["page"]]
    assert first["sources"][0]["dossier_document_id"] == ids["document"]


def test_a_question_the_dossier_cannot_answer_is_not_suggested_and_is_no_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = setup_dossier(client, ["Quel est le loyer ?", "Quelle est la superficie ?", "Et le parking ?"])
    use_searcher(monkeypatch, Searcher(ids))
    Llm(monkeypatch, {"Quel est le loyer ?": ANSWER, "Quelle est la superficie ?": NONE, "Et le parking ?": ANSWER})
    # Le dossier ne contient rien sur le parking : la recherche ne trouve rien.
    searcher = Searcher(ids)
    original = searcher.search

    async def search(query: str) -> list[SearchHit]:
        return [] if "parking" in query else await original(query)

    searcher.search = search  # type: ignore[method-assign]
    use_searcher(monkeypatch, searcher)

    run(client, ids)

    body = answers(client, ids)
    assert [a["question"] for a in body["answers"]] == ["Quel est le loyer ?"]
    assert body["status"] == "ready"
    assert [r.status for r in rows(client, ids)] == [
        QuestionAnswerStatus.REPONDUE,
        QuestionAnswerStatus.SANS_REPONSE,
        QuestionAnswerStatus.SANS_REPONSE,
    ]


def test_an_answer_that_is_up_to_date_is_never_computed_again(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = setup_dossier(client, ["Quel est le loyer ?"])
    use_searcher(monkeypatch, Searcher(ids))
    llm = Llm(monkeypatch, {"Quel est le loyer ?": ANSWER})
    run(client, ids)

    run(client, ids)

    assert llm.questions == ["Quel est le loyer ?"]  # un seul appel au modèle pour les deux passages


def test_a_changed_page_makes_the_answer_computed_again(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = setup_dossier(client, ["Quel est le loyer ?"])
    use_searcher(monkeypatch, Searcher(ids))
    llm = Llm(monkeypatch, {"Quel est le loyer ?": ANSWER})
    run(client, ids)

    async def edit() -> None:
        async with async_session_factory() as db:
            await db.execute(
                update(DocumentPage)
                .where(DocumentPage.id == uuid.UUID(ids["page"]))
                .values(content="Loyer : 900 euros.")
            )
            await db.commit()

    client.portal.call(edit)
    run(client, ids)

    assert len(llm.questions) == 2


def test_a_new_question_waits_for_the_next_analysis_and_a_removed_one_goes_with_it(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = setup_dossier(client, ["Quel est le loyer ?"])
    use_searcher(monkeypatch, Searcher(ids))
    Llm(monkeypatch, {"Quel est le loyer ?": ANSWER, "Et les charges ?": ANSWER})
    run(client, ids)

    client.put(f"/api/analyses/{ids['analyse']}/frequent-questions", json={"questions": ["Et les charges ?"]})
    run(client, ids, full=False)  # une correction : rien de neuf avant la relance
    assert [a["question"] for a in answers(client, ids)["answers"]] == ["Quel est le loyer ?"]

    run(client, ids, full=True)  # la fin d'une analyse : la liste de l'analyse fait foi
    assert [a["question"] for a in answers(client, ids)["answers"]] == ["Et les charges ?"]


def test_a_failing_question_does_not_stop_the_others_and_is_tried_again_next_time(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = setup_dossier(client, ["Quel est le loyer ?", "Qui est le bailleur ?"])
    use_searcher(monkeypatch, Searcher(ids))
    outcomes: dict[str, object] = {
        "Quel est le loyer ?": RuntimeError("modèle indisponible"),
        "Qui est le bailleur ?": ANSWER,
    }
    llm = Llm(monkeypatch, outcomes)

    run(client, ids)

    body = answers(client, ids)
    assert body["status"] == "failed"
    assert [a["question"] for a in body["answers"]] == ["Qui est le bailleur ?"]
    failed = rows(client, ids)[0]
    assert failed.status == QuestionAnswerStatus.ECHEC and "indisponible" in failed.error

    outcomes["Quel est le loyer ?"] = ANSWER
    run(client, ids)

    assert answers(client, ids)["status"] == "ready"
    assert llm.questions.count("Qui est le bailleur ?") == 1  # la réponse à jour n'a pas été recalculée


def test_without_an_index_nothing_is_written(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = setup_dossier(client, ["Quel est le loyer ?"])
    llm = Llm(monkeypatch, {"Quel est le loyer ?": ANSWER})

    async def no_index(dossier_id: uuid.UUID) -> bool:
        return False

    monkeypatch.setattr(job, "_index_ready", no_index)

    run(client, ids)

    assert rows(client, ids) == [] and llm.questions == []
    assert answers(client, ids) == {"status": "ready", "answers": []}


def test_an_analysis_without_question_has_no_answers(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = setup_dossier(client, [])
    llm = Llm(monkeypatch, {})

    run(client, ids)

    assert llm.questions == [] and answers(client, ids)["answers"] == []


def test_the_end_of_an_analysis_asks_for_the_answers(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[tuple] = []
    monkeypatch.setattr(agents_job, "dispatch_question_answers", lambda *args: asked.append(args))
    monkeypatch.setattr(agents_job, "dispatch_dossier_summary", lambda *args: None)
    ids = setup_dossier(client, ["Quel est le loyer ?"])

    async def finished() -> None:
        async def done(dossier_id: object) -> bool:
            return True

        monkeypatch.setattr(agents_job, "_wait_for_steps", done)
        await agents_job.run_agents(ids["dossier"])

    client.portal.call(finished)

    assert asked == [(ids["dossier"],)]


def test_a_correction_by_the_instructor_refreshes_the_existing_answers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.models.dossier_analysis import ElementVersionOrigin
    from app.repositories.dossier_analysis_repository import DossierAnalysisRepository

    asked: list[tuple] = []
    monkeypatch.setattr(dispatch, "dispatch_question_answers", lambda *args, **kwargs: asked.append((args, kwargs)))
    dossier_id, analysis, element = setup_analysis(client)

    async def correct(origin: ElementVersionOrigin) -> None:
        async with async_session_factory() as db:
            repository = DossierAnalysisRepository(db)
            fresh = await repository.get_element(analysis.id, element.id)
            await repository.add_version(fresh, value={"value": "Dupont"}, origin=origin)

    client.portal.call(correct, ElementVersionOrigin.MODEL)
    assert asked == []  # le modèle qui écrit l'analyse n'est pas une correction
    client.portal.call(correct, ElementVersionOrigin.INSTRUCTOR)

    assert asked == [((dossier_id,), {"full": False})]


def test_an_answer_left_in_progress_by_a_restart_becomes_a_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = setup_dossier(client, ["Quel est le loyer ?"])
    use_searcher(monkeypatch, Searcher(ids))
    Llm(monkeypatch, {"Quel est le loyer ?": ANSWER})
    run(client, ids)

    async def interrupt() -> None:
        async with async_session_factory() as db:
            await db.execute(
                update(DossierQuestionAnswer)
                .where(DossierQuestionAnswer.dossier_id == uuid.UUID(ids["dossier"]))
                .values(status=QuestionAnswerStatus.EN_COURS)
            )
            await db.commit()

        async def nobody(name: str) -> bool:
            return False

        await dispatch._fail_stale_question_answers(nobody)

    client.portal.call(interrupt)

    assert rows(client, ids)[0].status == QuestionAnswerStatus.ECHEC
    assert answers(client, ids)["status"] == "failed"


def test_a_dossier_the_person_cannot_see_does_not_reveal_its_answers(client: TestClient, world: dict) -> None:
    analyse = client.post("/api/analyses", json={"name": "Q", "description": "T"}).json()
    with As(world["alice"]):
        restricted = _create(client, analyse, visibility="restricted", groups=[world["a"]])
        assert client.get(f"/api/dossiers/{restricted['id']}/question-answers").status_code == 200
    with As(world["bob"]):  # groupe b : ne voit pas ce dossier
        assert client.get(f"/api/dossiers/{restricted['id']}/question-answers").status_code == 404
        assert client.post(f"/api/dossiers/{restricted['id']}/question-answers/regenerate").status_code == 404


def test_regenerating_asks_for_the_answers_again(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[tuple] = []
    import app.routers.dossier_question_answers as router

    monkeypatch.setattr(router, "dispatch_question_answers", lambda *args: asked.append(args))
    ids = setup_dossier(client, ["Quel est le loyer ?"])

    response = client.post(f"/api/dossiers/{ids['dossier']}/question-answers/regenerate")

    assert response.status_code == 202 and asked == [(ids["dossier"],)]
