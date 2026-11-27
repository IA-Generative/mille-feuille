import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import async_session_factory
from app.models.conversation import Message, MessageRole
from app.repositories.conversation_search_repository import search_terms, split_excerpt
from tests.access_support import As


def _word() -> str:
    """Un mot inventé propre à un test : la suite partage une base, une recherche ne doit trouver que ses messages."""
    return "zq" + "".join(chr(ord("a") + int(c, 16)) for c in uuid.uuid4().hex[:10])


def _dossier(client: TestClient, analyse: dict, name: str, **body) -> str:
    created = client.post("/api/dossiers", json={"name": name, "analyse_id": analyse["id"], **body})
    assert created.status_code in (200, 201), created.text
    return created.json()["id"]


def _conversation(client: TestClient, dossier_id: str) -> str:
    created = client.post(f"/api/dossiers/{dossier_id}/conversations")
    assert created.status_code in (200, 201), created.text
    return created.json()["id"]


def _say(client: TestClient, conversation_id: str, content: str, role: MessageRole = MessageRole.USER) -> str:
    async def add() -> str:
        async with async_session_factory() as db:
            message = Message(conversation_id=uuid.UUID(conversation_id), role=role, content=content)
            db.add(message)
            await db.commit()
            return str(message.id)

    return client.portal.call(add)


def _search(client: TestClient, query: str, **body) -> dict:
    response = client.post("/api/conversations/search", json={"query": query, **body})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_message_is_found_with_its_dossier_and_a_highlighted_excerpt(client, analyse) -> None:
    word = _word()
    dossier_id = _dossier(client, analyse, "Dossier à retrouver")
    conversation_id = _conversation(client, dossier_id)
    message_id = _say(client, conversation_id, f"Le **{word}** est-il joint au dossier ?")

    page = _search(client, word)

    assert page["total"] == 1
    result = page["items"][0]
    assert (result["dossier_id"], result["dossier_name"]) == (dossier_id, "Dossier à retrouver")
    assert result["conversation_id"] == conversation_id
    assert (result["match"]["message_id"], result["match"]["role"], result["match_count"]) == (message_id, "user", 1)
    assert [s["text"] for s in result["match"]["excerpt"] if s["highlighted"]] == [word]
    assert "*" not in "".join(s["text"] for s in result["match"]["excerpt"])


@pytest.mark.parametrize(
    "query",
    ["émargement", "emargement", "EMARGEMENTS", "émarge", "signées", "signee", "la feuille d'émargement"],
)
def test_accents_case_plurals_and_word_starts_are_tolerated(client, analyse, query) -> None:
    marker = _word()
    conversation_id = _conversation(client, _dossier(client, analyse, "Accents"))
    _say(client, conversation_id, f"{marker} La feuille d'émargement est signée.", MessageRole.ASSISTANT)

    page = _search(client, f"{marker} {query}")

    assert [r["conversation_id"] for r in page["items"]] == [conversation_id]
    assert any(s["highlighted"] for s in page["items"][0]["match"]["excerpt"])


def test_every_word_must_be_present(client, analyse) -> None:
    word, missing = _word(), _word()
    _say(client, _conversation(client, _dossier(client, analyse, "Tous les mots")), f"Voici {word}.")

    assert _search(client, f"{word} {missing}")["total"] == 0


def test_one_result_per_conversation_with_the_latest_match(client, analyse) -> None:
    word = _word()
    conversation_id = _conversation(client, _dossier(client, analyse, "Plusieurs messages"))
    _say(client, conversation_id, f"Premier {word}")
    latest = _say(client, conversation_id, f"Second {word}", MessageRole.ASSISTANT)

    result = _search(client, word)["items"][0]

    assert (result["match"]["message_id"], result["match_count"]) == (latest, 2)


def test_the_dossier_name_is_searched_too(client, analyse) -> None:
    word = _word()
    conversation_id = _conversation(client, _dossier(client, analyse, f"Subvention {word}"))

    page = _search(client, word)

    assert [r["conversation_id"] for r in page["items"]] == [conversation_id]
    assert (page["items"][0]["match"], page["items"][0]["match_count"]) == (None, 0)


def test_nobody_finds_the_messages_of_someone_else_not_even_an_admin(client, world, analyse) -> None:
    word = _word()
    with As(world["alice"]):
        _say(client, _conversation(client, _dossier(client, analyse, f"Partagé {word}")), f"Secret {word}")
        assert _search(client, word)["total"] == 1

    for other in ("bob", "root"):
        with As(world[other]):
            page = _search(client, word)
            assert (page["total"], page["items"]) == (0, [])


def test_a_dossier_that_is_no_longer_visible_disappears(client, world, analyse) -> None:
    word = _word()
    with As(world["alice"]):
        dossier_id = _dossier(client, analyse, f"Retiré {word}")
        _say(client, _conversation(client, dossier_id), f"Message {word}")
    with As(world["root"]):
        restricted = client.put(
            f"/api/dossiers/{dossier_id}/access",
            json={"visibility": "restricted", "group_paths": [world["root"].groups[1]]},
        )
        assert restricted.status_code == 200, restricted.text

    with As(world["alice"]):
        assert _search(client, word)["total"] == 0


def test_a_deleted_conversation_is_not_found_anymore(client, analyse) -> None:
    word = _word()
    dossier_id = _dossier(client, analyse, "Supprimée")
    conversation_id = _conversation(client, dossier_id)
    _say(client, conversation_id, f"À oublier {word}")

    assert client.delete(f"/api/dossiers/{dossier_id}/conversations/{conversation_id}").status_code == 204

    assert _search(client, word)["total"] == 0


def test_results_are_paginated(client, analyse) -> None:
    word = _word()
    for index in range(3):
        _say(client, _conversation(client, _dossier(client, analyse, f"Page {index}")), f"Mot {word}")

    first = _search(client, word, page_size=2)
    second = _search(client, word, page_size=2, page=2)

    assert (first["total"], len(first["items"]), len(second["items"])) == (3, 2, 1)
    assert {r["conversation_id"] for r in first["items"]}.isdisjoint(r["conversation_id"] for r in second["items"])


@pytest.mark.parametrize("query", ["& | !", "'); drop", "a:*", "::", "<-> ()"])
def test_search_operators_are_harmless(client, query) -> None:
    assert client.post("/api/conversations/search", json={"query": query}).status_code == 200


def test_too_short_or_too_long_queries_are_refused(client) -> None:
    for query in ("a", "x" * 201):
        assert client.post("/api/conversations/search", json={"query": query}).status_code == 422


def test_search_terms_and_excerpt_split() -> None:
    assert search_terms("d'émargement, n°12 a_b") == ["d", "émargement", "n", "12", "a", "b"]
    assert [(s.text, s.highlighted) for s in split_excerpt("a \x02b\x03\n c")] == [
        ("a ", False),
        ("b", True),
        (" c", False),
    ]
