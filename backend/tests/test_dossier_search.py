import logging
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError

from app.db import async_session_factory
from app.models.document_page import DocumentPage
from app.models.dossier import Dossier, DossierDocument, TextExtractionStatus
from app.models.dossier_analysis import AnalysisElementKind, ElementVersionOrigin
from app.models.dossier_event import DossierEvent
from app.repositories.dossier_analysis_repository import DossierAnalysisRepository
from app.repositories.dossier_search_repository import DossierSearchRepository, split_reference
from tests.access_support import As


def _word() -> str:
    """Un mot inventé propre à un test : la suite partage une base, une recherche ne doit trouver que ses dossiers."""
    return "zq" + "".join(chr(ord("a") + int(c, 16)) for c in uuid.uuid4().hex[:10])


def _dossier(client: TestClient, analyse: dict, name: str = "Dossier", **body) -> str:
    created = client.post("/api/dossiers", json={"name": name, "analyse_id": analyse["id"], **body})
    assert created.status_code in (200, 201), created.text
    return created.json()["id"]


def _document(client: TestClient, dossier_id: str, name: str = "piece.pdf", *pages: str) -> str:
    async def add() -> str:
        async with async_session_factory() as db:
            document = DossierDocument(
                dossier_id=uuid.UUID(dossier_id),
                name=name,
                size=1,
                s3_key=f"tests/{uuid.uuid4()}",
                mimetype="application/pdf",
                text_extraction_status=TextExtractionStatus.TERMINE,
            )
            document.pages = [DocumentPage(page_number=i, content=text) for i, text in enumerate(pages, start=1)]
            db.add(document)
            await db.commit()
            return str(document.id)

    return client.portal.call(add)


def _value(client: TestClient, dossier_id: str, value: str, *, rejected: bool = False) -> None:
    async def add() -> None:
        async with async_session_factory() as db:
            repository = DossierAnalysisRepository(db)
            analysis = await repository.get_current(uuid.UUID(dossier_id)) or await repository.create_analysis(
                uuid.UUID(dossier_id)
            )
            element = await repository.create_element(
                analysis,
                origin=ElementVersionOrigin.MODEL,
                kind=AnalysisElementKind.ENTITY,
                value={"value": value},
                definition_name="Nom du demandeur",
            )
            if rejected:
                await repository.add_version(
                    element,
                    value={"value": value},
                    origin=ElementVersionOrigin.INSTRUCTOR,
                    author_id="instructeur",
                    validation_status="rejeté",
                )

    client.portal.call(add)


def _reference_of(client: TestClient, dossier_id: str) -> str:
    async def read() -> str:
        async with async_session_factory() as db:
            return (await db.get(Dossier, uuid.UUID(dossier_id))).reference

    return client.portal.call(read)


def _search(client: TestClient, query: str, **body) -> dict:
    response = client.post("/api/search", json={"query": query, **body})
    assert response.status_code == 200, response.text
    return response.json()


def _ids(result: dict) -> list[str]:
    return [dossier["id"] for dossier in result["dossiers"]]


def _highlighted(excerpt: dict) -> list[str]:
    return [segment["text"] for segment in excerpt["segments"] if segment["highlighted"]]


def test_words_are_found_in_the_name_the_documents_the_values_and_the_pages(client, analyse) -> None:
    word = _word()
    by_name = _dossier(client, analyse, f"Demande {word}")
    by_document = _dossier(client, analyse)
    _document(client, by_document, f"attestation_{word}.pdf")
    by_value = _dossier(client, analyse)
    _value(client, by_value, f"Camille {word}")
    by_page = _dossier(client, analyse)
    document_id = _document(client, by_page, "bail.pdf", "Rien ici.", f"Le **logement** de {word} est loué.")

    result = _search(client, word)

    assert _ids(result) == [by_name, by_value, by_document, by_page]
    assert result["total"] == 4
    found = {dossier["id"]: dossier for dossier in result["dossiers"]}
    assert found[by_name]["excerpts"] == []
    assert found[by_name]["reference"].startswith("DOS-")
    assert found[by_name]["analyse_name"] == analyse["name"]
    assert found[by_value]["excerpts"][0]["field"] == "Nom du demandeur"
    assert found[by_document]["excerpts"][0]["document_name"] == f"attestation_{word}.pdf"
    page = found[by_page]["excerpts"][0]
    assert (page["document_id"], page["document_name"], page["page"]) == (document_id, "bail.pdf", 2)
    assert _highlighted(page) == [word]
    assert "*" not in "".join(segment["text"] for segment in page["segments"])


def test_every_word_is_required_but_may_be_spread_over_the_dossier(client, analyse) -> None:
    first, second = _word(), _word()
    spread = _dossier(client, analyse, f"Dossier {first}")
    _document(client, spread, "piece.pdf", f"Signé par {second}, émargement joint.")
    partial = _dossier(client, analyse, f"Dossier {first}")

    assert _ids(_search(client, f"{first} {second}")) == [spread]
    assert _ids(_search(client, f"{first} {second} EMARGEMENTS")) == [spread]
    assert sorted(_ids(_search(client, first))) == sorted([spread, partial])


def test_a_rejected_value_does_not_count(client, analyse) -> None:
    word = _word()
    _value(client, _dossier(client, analyse), word, rejected=True)

    assert _search(client, word) == {"dossiers": [], "total": 0}


def test_an_added_or_deleted_document_is_taken_into_account(client, analyse) -> None:
    word = _word()
    dossier_id = _dossier(client, analyse)
    assert _ids(_search(client, word)) == []

    document_id = _document(client, dossier_id, "piece.pdf", f"Texte {word}")
    assert _ids(_search(client, word)) == [dossier_id]

    async def remove() -> None:
        async with async_session_factory() as db:
            await db.execute(delete(DossierDocument).where(DossierDocument.id == uuid.UUID(document_id)))
            await db.commit()

    client.portal.call(remove)
    assert _ids(_search(client, word)) == []


def test_a_restricted_dossier_never_shows_outside_its_groups(client, world, analyse) -> None:
    word = _word()
    with As(world["alice"]):
        dossier_id = _dossier(client, analyse, f"Secret {word}", visibility="restricted", group_ids=[world["a"]])
        _document(client, dossier_id, f"{word}.pdf", f"Page {word}")
        _value(client, dossier_id, word)
        assert _ids(_search(client, word)) == [dossier_id]
    with As(world["bob"]):
        assert _search(client, word) == {"dossiers": [], "total": 0}
        assert _search(client, _reference_of(client, dossier_id))["total"] == 0


def test_a_dossier_is_found_by_its_reference(client, analyse, world) -> None:
    with As(world["alice"]):
        dossier_id = _dossier(client, analyse, visibility="restricted", group_ids=[world["a"]])
    reference = _reference_of(client, dossier_id)

    with As(world["alice"]):
        assert _ids(_search(client, reference.lower())) == [dossier_id]


def test_an_administrator_reading_an_excerpt_outside_their_groups_is_traced(client, world, analyse) -> None:
    word = _word()
    with As(world["bob"]):
        shown = _dossier(client, analyse, visibility="restricted", group_ids=[world["b"]])
        _document(client, shown, "piece.pdf", f"Page {word}")
        name_only = _dossier(client, analyse, word, visibility="restricted", group_ids=[world["b"]])

    with As(world["root"]):
        assert sorted(_ids(_search(client, word))) == sorted([shown, name_only])

    async def traced() -> set[str]:
        async with async_session_factory() as db:
            rows = await db.scalars(
                select(DossierEvent.dossier_id).where(
                    DossierEvent.type == "admin_access", DossierEvent.actor_id == world["root"].user_id
                )
            )
            return {str(row) for row in rows}

    assert client.portal.call(traced) == {shown}


def test_the_number_of_results_is_limited_and_the_total_is_given(client, analyse) -> None:
    word = _word()
    for _ in range(3):
        _dossier(client, analyse, word)

    result = _search(client, word, limit=2)

    assert (len(result["dossiers"]), result["total"]) == (2, 3)


def test_a_failure_does_not_log_the_searched_words(client, monkeypatch, caplog) -> None:
    word = _word()

    async def fail(*args, **kwargs):
        raise OperationalError("SELECT", {"q": word}, Exception(word))

    monkeypatch.setattr(DossierSearchRepository, "search", fail)
    with caplog.at_level(logging.DEBUG):
        response = client.post("/api/search", json={"query": word})

    assert response.status_code == 503
    assert "OperationalError" in caplog.text
    assert word not in caplog.text and word not in response.text


def test_the_reference_is_separated_from_the_words() -> None:
    assert split_reference("dos-2026-0012") == ((2026, 12), " ")
    assert split_reference("Camille") == (None, "Camille")
