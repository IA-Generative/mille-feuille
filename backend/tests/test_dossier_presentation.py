"""La présentation d'un dossier, en tête de sa conversation : composée de ce que l'analyse a produit, sans modèle.
Choisir une question suggérée fait entrer l'échange dans la conversation. La base est réelle."""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.db import async_session_factory
from app.models.dossier import Dossier, DossierStatus, ExecutionStep, ExecutionStepKind, ExecutionStepStatus
from app.models.dossier_analysis import ElementVersionOrigin
from app.models.question_answer import DossierQuestionAnswer, QuestionAnswerStatus
from app.models.summary import SummaryStatus
from app.repositories.dossier_analysis_repository import DossierAnalysisRepository
from app.repositories.dossier_repository import DossierRepository
from tests.access_support import As
from tests.test_dossier_access import _create

INTERNAL = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


def new_dossier(client: TestClient) -> dict:
    analyse = client.post("/api/analyses", json={"name": f"Pré {uuid.uuid4().hex[:6]}", "description": "T"}).json()
    dossier = _create(client, analyse, visibility="analyse")
    client.post(
        f"/api/dossiers/{dossier['id']}/documents", files=[("files", ("bail.pdf", b"fake-bytes", "application/pdf"))]
    )
    document = client.get(f"/api/dossiers/{dossier['id']}").json()["documents"][0]
    for number in (1, 2):
        client.post(
            f"/api/internal/documents/{document['id']}/pages",
            json={"page_number": number, "content": f"Page {number}"},
            headers=INTERNAL,
        )
    return {"id": dossier["id"], "document": document["id"]}


def set_status(client: TestClient, dossier_id: str, status: DossierStatus) -> None:
    async def work() -> None:
        async with async_session_factory() as db:
            await db.execute(update(Dossier).where(Dossier.id == uuid.UUID(dossier_id)).values(status=status))
            await db.commit()

    client.portal.call(work)


def add_step(client: TestClient, dossier_id: str, kind: ExecutionStepKind, label: str, output: str, ok: bool = True):
    async def work() -> None:
        async with async_session_factory() as db:
            db.add(
                ExecutionStep(
                    dossier_id=uuid.UUID(dossier_id),
                    kind=kind,
                    label=label,
                    status=ExecutionStepStatus.TERMINE if ok else ExecutionStepStatus.ECHEC,
                    started_at=datetime.now(UTC),
                    output=output,
                )
            )
            await db.commit()

    client.portal.call(work)


def add_answer(
    client: TestClient,
    dossier_id: str,
    question: str,
    position: int,
    status=QuestionAnswerStatus.REPONDUE,
    sources=None,
) -> str:
    async def work() -> str:
        async with async_session_factory() as db:
            row = DossierQuestionAnswer(
                dossier_id=uuid.UUID(dossier_id),
                question=question,
                position=position,
                status=status,
                answer=f"Réponse à {question} [1]" if status == QuestionAnswerStatus.REPONDUE else None,
                sources=sources or [],
            )
            db.add(row)
            await db.commit()
            return str(row.id)

    return client.portal.call(work)


def presentation(client: TestClient, dossier_id: str) -> dict:
    return client.get(f"/api/dossiers/{dossier_id}/presentation").json()


def test_a_dossier_not_yet_analysed_has_nothing_to_present(client: TestClient) -> None:
    dossier = new_dossier(client)

    body = presentation(client, dossier["id"])

    assert body["status"] == "idle" and body["summary"] is None and body["suggestions"] == []
    assert [d["name"] for d in body["documents"]] == ["bail.pdf"] and body["documents"][0]["page_count"] == 2


def test_while_the_analysis_runs_there_is_no_partial_summary_and_no_suggestion(client: TestClient) -> None:
    dossier = new_dossier(client)
    add_answer(client, dossier["id"], "Quel est le loyer ?", 0)
    add_step(client, dossier["id"], ExecutionStepKind.AGENT, "Juriste", "Une synthèse")
    set_status(client, dossier["id"], DossierStatus.EN_COURS)

    body = presentation(client, dossier["id"])

    assert body["status"] == "pending"
    assert body["summary"] is None and body["agents"] == [] and body["suggestions"] == []


def test_a_finished_analysis_is_presented_with_everything_it_produced(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # La correction de l'instructeur rafraîchirait les réponses prêtes : pas de vrai travail ici.
    monkeypatch.setattr("app.agent.dispatch.dispatch_question_answers", lambda *args, **kwargs: None)
    dossier = new_dossier(client)
    dossier_id = dossier["id"]
    add_step(
        client, dossier_id, ExecutionStepKind.CLASSIFICATION, "Classification", "Bail d'habitation (confiance : 94%)"
    )
    add_step(client, dossier_id, ExecutionStepKind.AGENT, "Juriste", "Le bail est conforme.")
    add_step(client, dossier_id, ExecutionStepKind.AGENT, "Silencieux", "")
    add_answer(client, dossier_id, "Qui est le bailleur ?", 1)
    add_answer(
        client, dossier_id, "Quel est le loyer ?", 0, sources=[{"number": 1, "page_ids": ["p1"], "excerpt": "800 €"}]
    )
    add_answer(client, dossier_id, "Et le parking ?", 2, status=QuestionAnswerStatus.SANS_REPONSE)

    async def produce() -> None:
        async with async_session_factory() as db:
            repository = DossierRepository(db)
            await repository.add_dossier_summary(
                await repository.get(uuid.UUID(dossier_id)), content="Un bail de trois ans."
            )
            analyses = DossierAnalysisRepository(db)
            analysis = await analyses.create_analysis(uuid.UUID(dossier_id))
            from app.models.dossier_analysis import AnalysisElementKind

            element = await analyses.create_element(
                analysis,
                kind=AnalysisElementKind.ENTITY,
                value={"value": "Dupond"},
                definition_name="Bailleur",
                origin=ElementVersionOrigin.MODEL,
            )
            await analyses.add_version(element, value={"value": "Dupont"}, origin=ElementVersionOrigin.INSTRUCTOR)

    client.portal.call(produce)
    set_status(client, dossier_id, DossierStatus.TERMINE)

    body = presentation(client, dossier_id)

    assert body["status"] == "ready"
    assert body["summary"] == "Un bail de trois ans."
    assert body["classification"] == {"label": "Bail d'habitation", "confidence": 94}
    assert [(e["name"], e["value"]) for e in body["entities"]] == [("Bailleur", "Dupont")]  # la correction fait foi
    assert [(a["name"], a["output"]) for a in body["agents"]] == [("Juriste", "Le bail est conforme.")]
    # Dans l'ordre de l'analyse ; la question sans réponse n'est pas suggérée.
    assert [s["question"] for s in body["suggestions"]] == ["Quel est le loyer ?", "Qui est le bailleur ?"]
    assert body["suggestions"][0]["sources"][0]["excerpt"] == "800 €"


def test_a_failed_analysis_says_why(client: TestClient) -> None:
    dossier = new_dossier(client)
    add_step(
        client, dossier["id"], ExecutionStepKind.CLASSIFICATION, "Classification", "Le service ne répond pas", ok=False
    )
    set_status(client, dossier["id"], DossierStatus.ECHEC)

    body = presentation(client, dossier["id"])

    assert body["status"] == "failed" and body["error"] == "Le service ne répond pas"
    assert body["suggestions"] == []


def test_a_dossier_the_person_cannot_see_has_no_presentation(client: TestClient, world: dict) -> None:
    analyse = client.post("/api/analyses", json={"name": "P", "description": "T"}).json()
    with As(world["alice"]):
        restricted = _create(client, analyse, visibility="restricted", groups=[world["a"]])
        assert client.get(f"/api/dossiers/{restricted['id']}/presentation").status_code == 200
    with As(world["bob"]):  # groupe b : ne voit pas ce dossier
        assert client.get(f"/api/dossiers/{restricted['id']}/presentation").status_code == 404


def open_conversation(client: TestClient, dossier_id: str) -> dict:
    return client.post(f"/api/dossiers/{dossier_id}/conversations").json()


def ask_url(dossier_id: str, conversation_id: str, answer_id: str) -> str:
    return f"/api/dossiers/{dossier_id}/conversations/{conversation_id}/question-answers/{answer_id}/ask"


def test_choosing_a_suggestion_adds_the_question_and_its_ready_answer_without_the_model(client: TestClient) -> None:
    dossier = new_dossier(client)
    answer_id = add_answer(
        client,
        dossier["id"],
        "Quel est le loyer ?",
        0,
        sources=[{"number": 1, "dossier_document_id": dossier["document"], "page_ids": [], "excerpt": "800 €"}],
    )
    conversation = open_conversation(client, dossier["id"])

    response = client.post(ask_url(dossier["id"], conversation["id"], answer_id))

    assert response.status_code == 200
    first, second = response.json()
    assert (first["role"], first["content"]) == ("user", "Quel est le loyer ?")
    assert (second["role"], second["content"]) == ("assistant", "Réponse à Quel est le loyer ? [1]")
    assert second["sources"][0]["excerpt"] == "800 €" and second["sources"][0]["number"] == 1
    history = client.get(f"/api/dossiers/{dossier['id']}/conversations/{conversation['id']}/messages").json()["items"]
    assert [m["role"] for m in history] == ["user", "assistant"]


def test_a_suggestion_can_only_be_asked_in_ones_own_conversation_and_when_its_answer_is_ready(
    client: TestClient, world: dict
) -> None:
    analyse = client.post("/api/analyses", json={"name": "P", "description": "T"}).json()
    dossier = _create(client, analyse, visibility="analyse")
    ready = add_answer(client, dossier["id"], "Quel est le loyer ?", 0)
    none = add_answer(client, dossier["id"], "Et le parking ?", 1, status=QuestionAnswerStatus.SANS_REPONSE)
    with As(world["alice"]):
        conversation = open_conversation(client, dossier["id"])
        assert client.post(ask_url(dossier["id"], conversation["id"], none)).status_code == 404
        assert client.post(ask_url(dossier["id"], conversation["id"], str(uuid.uuid4()))).status_code == 404
    with As(world["bob"]):  # la conversation d'alice n'est pas la sienne
        assert client.post(ask_url(dossier["id"], conversation["id"], ready)).status_code == 404


def test_the_presentation_is_still_refreshing_while_the_answers_are_not_computed(client: TestClient) -> None:
    analyse = client.post("/api/analyses", json={"name": "P", "description": "T"}).json()
    client.put(f"/api/analyses/{analyse['id']}/frequent-questions", json={"questions": ["Quel est le loyer ?"]})
    dossier = _create(client, analyse, visibility="analyse")
    set_status(client, dossier["id"], DossierStatus.TERMINE)

    assert presentation(client, dossier["id"])["refreshing"] is True  # le calcul n'a pas commencé

    answer_id = add_answer(client, dossier["id"], "Quel est le loyer ?", 0, status=QuestionAnswerStatus.EN_COURS)
    assert presentation(client, dossier["id"])["refreshing"] is True  # en cours

    async def finish() -> None:
        async with async_session_factory() as db:
            await db.execute(
                update(DossierQuestionAnswer)
                .where(DossierQuestionAnswer.id == uuid.UUID(answer_id))
                .values(status=QuestionAnswerStatus.SANS_REPONSE)
            )
            await db.commit()

    client.portal.call(finish)
    assert presentation(client, dossier["id"])["refreshing"] is False


def test_a_failed_summary_is_reported_so_that_one_can_try_again(client: TestClient) -> None:
    dossier = new_dossier(client)
    set_status(client, dossier["id"], DossierStatus.TERMINE)

    async def fail() -> None:
        async with async_session_factory() as db:
            await db.execute(
                update(Dossier)
                .where(Dossier.id == uuid.UUID(dossier["id"]))
                .values(summary_status=SummaryStatus.ECHEC, summary_error="Le modèle ne répond pas")
            )
            await db.commit()

    client.portal.call(fail)

    body = presentation(client, dossier["id"])

    assert body["status"] == "ready" and body["summary"] is None
    assert body["summary_error"] == "Le modèle ne répond pas"
