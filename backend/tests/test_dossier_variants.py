"""Rapprochements souples (#648) : le jeu de cas qui en mesure la qualité, puis leur présentation."""

from sqlalchemy import text

from app.db import async_session_factory
from tests.access_support import As
from tests.test_dossier_search import _dossier, _search, _value, _word

# (une écriture, une autre, doivent-elles être rapprochées ?). À compléter avec des cas tirés de vrais dossiers.
CASES = [
    ("Émile Durand", "Durand Emile", True),
    ("DURAND, Émile", "emile durand", True),
    ("Jean-Pierre Martin", "Martin Jean Pierre", True),
    ("AB-123-CD", "AB123CD", True),
    ("AB 123 CD", "ab.123.cd", True),
    ("PERMIS-000123", "PERMIS OOO123", True),
    ("FR76 3000 1007", "FR7630001007", True),
    ("12 av. des Lilas", "12 avenue des Lilas", True),
    ("3 bd Victor Hugo", "3 boulevard Victor-Hugo", True),
    ("8 r. de la Gare", "8 rue de la Gare", True),
    ("Émile Durand", "Émile Durant", False),
    ("Émile Durand", "Emilie Durand", False),
    ("AB-123-CD", "AB-132-CD", False),
    ("12 rue des Lilas", "21 rue des Lilas", False),
    ("R. Martin", "Rue Martin", False),
    ("Transports Martin", "Transports Martins", False),
]


def test_the_quality_of_the_variant_key_on_the_case_set(client) -> None:
    async def same(first: str, second: str) -> bool:
        async with async_session_factory() as db:
            query = text(
                "SELECT dossier_link_loose_key(dossier_link_key(:a)) = dossier_link_loose_key(dossier_link_key(:b))"
            )
            return await db.scalar(query, {"a": first, "b": second})

    wrong = [(a, b) for a, b, expected in CASES if client.portal.call(same, a, b) is not expected]

    assert wrong == []


def test_variants_link_only_when_enabled_and_are_marked_uncertain(client, analyse, monkeypatch) -> None:
    word, name = _word(), _word()
    first, second = _dossier(client, analyse, word), _dossier(client, analyse, word)
    _value(client, first, f"Camille {name}")
    _value(client, second, f"{name.upper()}, Camille")
    assert _search(client, word)["items"] == []

    monkeypatch.setenv("SEARCH_VARIANT_LINKS_ENABLED", "true")
    [item] = _search(client, word)["items"]

    assert (item["uncertain"], sorted(item["dossier_ids"])) == (True, sorted([first, second]))
    # Chaque écriture est montrée : c'est ce qui permet de juger.
    assert sorted(o["text"] for o in item["occurrences"]) == sorted([f"Camille {name}", f"{name.upper()}, Camille"])
    links = client.post("/api/search/links", json={"dossier_ids": [first]}).json()
    assert [d["id"] for d in links["dossiers"]] == [first, second]


def test_identical_values_are_not_repeated_as_a_variant(client, analyse, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_VARIANT_LINKS_ENABLED", "true")
    word, name = _word(), _word()
    for _ in range(2):
        _value(client, _dossier(client, analyse, word), name)

    assert [item["uncertain"] for item in _search(client, word)["items"]] == [False]


def test_hidden_counts_ignore_variants(client, world, analyse, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_VARIANT_LINKS_ENABLED", "true")
    monkeypatch.setenv("SEARCH_HIDDEN_LINKS_ENABLED", "true")
    word, name = _word(), _word()
    with As(world["bob"]):
        secret = _dossier(client, analyse, visibility="restricted", group_ids=[world["b"]])
        _value(client, secret, f"{name} Camille")
    with As(world["alice"]):
        mine = _dossier(client, analyse, word, visibility="restricted", group_ids=[world["a"]])
        _value(client, mine, f"Camille {name}")
        result = _search(client, word)

    assert (result["items"], result["hidden"]) == ([], [])
