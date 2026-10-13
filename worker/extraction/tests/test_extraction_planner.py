"""Tests du découpage de l'extraction et des empreintes (issue #126)."""

from types import SimpleNamespace

from app import fingerprint
from app.extraction_planner import (
    estimate_tokens,
    group_definitions,
    new_entities,
    normalize_value,
    plan_lots,
    text_budget,
)


def _pages(*lengths: int) -> list[dict]:
    return [{"page_number": i + 1, "content": "x" * n, "id": f"page-{i + 1}"} for i, n in enumerate(lengths)]


def _numbers(lots: list[list[dict]]) -> list[list[int]]:
    return [[p["page_number"] for p in lot] for lot in lots]


# --- Groupes de définitions ---


def test_definitions_are_grouped_by_fixed_size_in_order() -> None:
    definitions = [{"id": str(i), "name": f"e{i}"} for i in range(5)]
    groups = group_definitions(definitions, 2)
    assert [[d["name"] for d in g] for g in groups] == [["e0", "e1"], ["e2", "e3"], ["e4"]]


def test_adding_a_definition_at_the_end_only_changes_the_last_group() -> None:
    before = group_definitions([{"id": str(i)} for i in range(4)], 2)
    after = group_definitions([{"id": str(i)} for i in range(5)], 2)
    assert after[0] == before[0] and after[1] == before[1]
    assert len(after) == 3


def test_inserting_a_definition_in_the_middle_shifts_the_following_groups() -> None:
    ids = ["a", "b", "c", "d"]
    before = group_definitions([{"id": i} for i in ids], 2)
    after = group_definitions([{"id": i} for i in ["a", "x", "b", "c", "d"]], 2)
    assert after[0] != before[0] and after[1] != before[1]


def test_zero_group_size_gives_a_single_group_and_no_definition_gives_none() -> None:
    definitions = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    assert group_definitions(definitions, 0) == [definitions]
    assert group_definitions([], 8) == []


# --- Budget de jetons ---


def test_token_estimate_is_about_four_characters_per_token() -> None:
    assert estimate_tokens("a" * 400) == 100
    assert estimate_tokens("") == 1
    assert estimate_tokens(None) == 1


def test_text_budget_subtracts_output_prompt_and_definitions() -> None:
    small = text_budget(max_tokens=8000, reserved_output_tokens=1500, prompt="p", definitions=[])
    big_prompt = text_budget(max_tokens=8000, reserved_output_tokens=1500, prompt="p" * 4000, definitions=[])
    with_defs = text_budget(
        max_tokens=8000,
        reserved_output_tokens=1500,
        prompt="p",
        definitions=[{"name": "nom", "type": "texte", "definition": "d" * 800}],
    )
    assert small < 8000 - 1500
    assert big_prompt < small
    assert with_defs < small


def test_text_budget_keeps_a_minimum() -> None:
    assert text_budget(max_tokens=100, reserved_output_tokens=90, prompt="p" * 4000, definitions=[]) >= 500


# --- Lots de pages ---


def test_a_document_that_fits_the_budget_is_a_single_lot() -> None:
    assert _numbers(plan_lots(_pages(400, 400, 400), budget=10_000, overlap=1)) == [[1, 2, 3]]


def test_no_pages_gives_no_lot() -> None:
    assert plan_lots([], budget=1000, overlap=1) == []


def test_lots_are_defined_by_the_token_budget_not_by_a_page_count() -> None:
    # 4 pages de ~100 jetons (+ surcoût) avec un budget de ~250 : 2 pages par lot.
    pages = _pages(400, 400, 400, 400)
    assert _numbers(plan_lots(pages, budget=250, overlap=0)) == [[1, 2], [3, 4]]
    # Pages courtes : davantage de pages dans le même budget.
    short = _pages(40, 40, 40, 40, 40, 40)
    assert _numbers(plan_lots(short, budget=250, overlap=0)) == [[1, 2, 3, 4, 5, 6]]


def test_consecutive_lots_overlap_by_the_configured_number_of_pages() -> None:
    pages = _pages(400, 400, 400, 400, 400)
    assert _numbers(plan_lots(pages, budget=250, overlap=1)) == [[1, 2], [2, 3], [3, 4], [4, 5]]
    assert _numbers(plan_lots(pages, budget=330, overlap=1)) == [[1, 2, 3], [3, 4, 5]]


def test_overlap_never_prevents_progress() -> None:
    pages = _pages(400, 400, 400)
    # Recouvrement plus grand que le lot : on avance quand même d'une page.
    lots = plan_lots(pages, budget=250, overlap=5)
    assert _numbers(lots) == [[1, 2], [2, 3]]


def test_an_oversized_page_forms_its_own_lot() -> None:
    pages = _pages(100, 40_000, 100)
    lots = _numbers(plan_lots(pages, budget=250, overlap=0))
    assert [2] in lots
    assert sorted(p for lot in lots for p in lot) == [1, 2, 3]


def test_every_page_is_covered_by_at_least_one_lot() -> None:
    pages = _pages(*([300] * 23))
    covered = {p["page_number"] for lot in plan_lots(pages, budget=400, overlap=1) for p in lot}
    assert covered == set(range(1, 24))


# --- Fusion des doublons dus au recouvrement ---


def _entity(name: str, value: str):
    return SimpleNamespace(entity_name=name, value=value)


def test_duplicates_across_lots_are_merged_by_definition_and_value() -> None:
    seen: set[tuple[str, str]] = set()
    first = new_entities([_entity("nom", "Dupont"), _entity("adresse", "1 rue X")], seen)
    second = new_entities([_entity("nom", "  dupont "), _entity("adresse", "2 rue Y")], seen)
    assert [e.value for e in first] == ["Dupont", "1 rue X"]
    # Même définition et même valeur (casse et espaces ignorés) : écarté.
    assert [e.value for e in second] == ["2 rue Y"]


def test_same_value_for_another_definition_is_kept() -> None:
    seen: set[tuple[str, str]] = set()
    new_entities([_entity("nom", "Paris")], seen)
    assert [e.entity_name for e in new_entities([_entity("ville", "Paris")], seen)] == ["ville"]


def test_normalize_value() -> None:
    assert normalize_value("  Jean   DUPONT ") == "jean dupont"
    assert normalize_value(None) == ""


# --- Empreintes ---

DEFS = [{"id": "d1", "name": "nom", "type": "texte", "definition": "Nom de famille"}]
LOT = [{"page_number": 1, "content": "Nom: Dupont"}, {"page_number": 2, "content": "Adresse"}]


def test_extraction_fingerprint_is_stable_for_identical_inputs() -> None:
    first = fingerprint.extraction_fingerprint(LOT, DEFS, "Extrais.")
    again = fingerprint.extraction_fingerprint([dict(p) for p in LOT], [dict(d) for d in DEFS], "Extrais.")
    assert first == again
    assert len(first) == 64


def test_extraction_fingerprint_ignores_the_page_id_and_extra_fields() -> None:
    with_ids = [{**p, "id": f"id-{i}", "screenshot_key": "k"} for i, p in enumerate(LOT)]
    assert fingerprint.extraction_fingerprint(with_ids, DEFS, "Extrais.") == fingerprint.extraction_fingerprint(
        LOT, DEFS, "Extrais."
    )


def test_extraction_fingerprint_changes_with_each_input() -> None:
    base = fingerprint.extraction_fingerprint(LOT, DEFS, "Extrais.")
    changed_text = [{**LOT[0], "content": "Nom: Durand"}, LOT[1]]
    changed_definition = [{**DEFS[0], "definition": "Nom d'usage"}]
    extra_definition = DEFS + [{"id": "d2", "name": "prenom", "type": "texte", "definition": "Prénom"}]
    renumbered = [{**LOT[0], "page_number": 5}, LOT[1]]
    others = {
        fingerprint.extraction_fingerprint(changed_text, DEFS, "Extrais."),
        fingerprint.extraction_fingerprint(LOT, changed_definition, "Extrais."),
        fingerprint.extraction_fingerprint(LOT, extra_definition, "Extrais."),
        fingerprint.extraction_fingerprint(LOT, DEFS, "Extrais autrement."),
        fingerprint.extraction_fingerprint(renumbered, DEFS, "Extrais."),
        fingerprint.extraction_fingerprint(LOT[:1], DEFS, "Extrais."),
    }
    assert base not in others
    assert len(others) == 6


def test_fingerprint_changes_with_the_model_and_the_pipeline_version(monkeypatch) -> None:
    base = fingerprint.extraction_fingerprint(LOT, DEFS, "Extrais.")
    monkeypatch.setattr(fingerprint.settings, "LLM_MODEL", "un-autre-modele")
    assert fingerprint.extraction_fingerprint(LOT, DEFS, "Extrais.") != base
    monkeypatch.undo()
    monkeypatch.setattr(fingerprint, "PIPELINE_VERSION", "pipeline-2")
    assert fingerprint.extraction_fingerprint(LOT, DEFS, "Extrais.") != base
