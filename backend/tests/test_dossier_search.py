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

    assert _search(client, word) == {"dossiers": [], "total": 0, "items": [], "hidden": []}


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
        assert _search(client, word) == {"dossiers": [], "total": 0, "items": [], "hidden": []}
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


def _hash(client: TestClient, document_id: str, file_hash: str) -> None:
    async def write() -> None:
        async with async_session_factory() as db:
            (await db.get(DossierDocument, uuid.UUID(document_id))).file_hash = file_hash
            await db.commit()

    client.portal.call(write)


def test_results_are_linked_by_equal_values_and_identical_files(client, analyse) -> None:
    word, shared = _word(), _word()
    first, second = _dossier(client, analyse, word), _dossier(client, analyse, word)
    _value(client, first, f"Émile   {shared}")
    _value(client, second, f"emile {shared.upper()}")
    file_hash = uuid.uuid4().hex * 2
    for dossier_id in (first, second):
        _hash(client, _document(client, dossier_id, "attestation.pdf"), file_hash)

    items = {item["kind"]: item for item in _search(client, word)["items"]}

    assert sorted(items) == ["document", "value"]
    assert sorted(items["value"]["dossier_ids"]) == sorted([first, second])
    assert items["value"]["occurrences"][0]["origin"] == f"Analyse {analyse['name']} · Nom du demandeur"
    assert items["document"]["label"] == "attestation.pdf"


def test_a_link_never_mentions_a_dossier_outside_the_results(client, world, analyse) -> None:
    word, shared = _word(), _word()
    with As(world["bob"]):
        secret = _dossier(client, analyse, word, visibility="restricted", group_ids=[world["b"]])
        _value(client, secret, shared)
    with As(world["alice"]):
        visible = _dossier(client, analyse, word, visibility="restricted", group_ids=[world["a"]])
        _value(client, visible, shared)
        result = _search(client, word)

        assert _ids(result) == [visible]
        assert result["items"] == []


def test_a_rejected_or_empty_value_links_nothing(client, analyse) -> None:
    word, shared = _word(), _word()
    first, second = _dossier(client, analyse, word), _dossier(client, analyse, word)
    for dossier_id in (first, second):
        _value(client, dossier_id, "oui")
    _value(client, first, shared)
    _value(client, second, shared, rejected=True)

    assert _search(client, word)["items"] == []


def test_a_value_shared_by_too_many_dossiers_links_nothing(client, analyse, monkeypatch) -> None:
    monkeypatch.setattr("app.repositories.dossier_link_repository.COMMON_FLOOR", 2)
    monkeypatch.setattr("app.repositories.dossier_link_repository.COMMON_SHARE", 0)
    word, shared = _word(), _word()
    for _ in range(3):
        _value(client, _dossier(client, analyse, word), shared)

    assert _search(client, word)["items"] == []


def _links(client: TestClient, ids: list[str], **body):
    return client.post("/api/search/links", json={"dossier_ids": ids, **body})


def test_chosen_dossiers_show_what_links_them_and_who_else(client, analyse) -> None:
    first_value, second_value = _word(), _word()
    first, second, bridge, apart = (_dossier(client, analyse) for _ in range(4))
    _value(client, first, first_value)
    _value(client, bridge, first_value)
    _value(client, bridge, second_value)
    _value(client, second, second_value)

    result = _links(client, [second, first]).json()

    assert result["anchor_ids"] == [second, first]
    assert _ids(result) == [second, first, bridge]
    assert sorted(item["label"] for item in result["items"]) == sorted([first_value, second_value])
    alone = _links(client, [first, second], include_related=False).json()
    assert (_ids(alone), alone["items"]) == ([first, second], [])
    assert _links(client, [apart]).json()["items"] == []


def test_a_hidden_dossier_is_neither_a_start_nor_a_link(client, world, analyse) -> None:
    value = _word()
    with As(world["bob"]):
        secret = _dossier(client, analyse, visibility="restricted", group_ids=[world["b"]])
        _value(client, secret, value)
    with As(world["alice"]):
        mine = _dossier(client, analyse, visibility="restricted", group_ids=[world["a"]])
        _value(client, mine, value)

        refused = _links(client, [mine, secret])
        assert refused.status_code == 404
        assert refused.json()["detail"]["dossier_ids"] == [secret]
        result = _links(client, [mine]).json()
        assert (_ids(result), result["items"]) == ([mine], [])


def test_picking_by_name_skips_the_details(client, analyse) -> None:
    word = _word()
    _document(client, _dossier(client, analyse, word), "piece.pdf", word)

    result = _search(client, word, details=False)

    assert (result["total"], result["dossiers"][0]["excerpts"], result["items"]) == (1, [], [])


def test_hidden_linked_dossiers_are_only_counted_when_enabled(client, world, analyse, monkeypatch) -> None:
    word, value = _word(), _word()
    with As(world["bob"]):
        secret = _dossier(client, analyse, "Nom secret", visibility="restricted", group_ids=[world["b"]])
        _value(client, secret, value)
    with As(world["alice"]):
        mine = _dossier(client, analyse, word, visibility="restricted", group_ids=[world["a"]])
        _value(client, mine, value)
        assert _search(client, word)["hidden"] == []

        monkeypatch.setenv("SEARCH_HIDDEN_LINKS_ENABLED", "true")
        for response in (client.post("/api/search", json={"query": word}), _links(client, [mine])):
            assert response.json()["hidden"] == [{"theme_name": None, "count": 1, "dossier_ids": [mine]}]
            assert secret not in response.text and "Nom secret" not in response.text
        # Sans résultat accessible, rien.
        assert _search(client, "secret " + value)["hidden"] == []

        monkeypatch.setenv("SEARCH_HIDDEN_LINKS_MIN", "2")
        assert _search(client, word)["hidden"] == []
        monkeypatch.delenv("SEARCH_HIDDEN_LINKS_MIN")
    with As(world["root"]):
        assert _search(client, word)["hidden"] == []
