"""Localisation d'une valeur extraite : de son span ou de sa valeur aux rectangles de la page."""

from app.locate import find_spans, rects_for_span


def _word(text: str, start: int, x_min: float, x_max: float, y: float) -> dict:
    return {
        "text": text,
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y,
        "y_max": round(y + 0.02, 2),
        "char_start": start,
        "char_end": start + len(text),
    }


# Contenu : « Nom : Dupont\nJean Pierre » (Dupont = 6-12, Jean = 13-17, Pierre = 18-24).
LINES = [
    {
        "text": "Nom : Dupont",
        "x_min": 0.1,
        "x_max": 0.5,
        "y_min": 0.1,
        "y_max": 0.12,
        "char_start": 0,
        "char_end": 12,
        "words": [_word("Nom", 0, 0.1, 0.2, 0.1), _word(":", 4, 0.22, 0.23, 0.1), _word("Dupont", 6, 0.3, 0.5, 0.1)],
    },
    {
        "text": "Jean Pierre",
        "x_min": 0.1,
        "x_max": 0.4,
        "y_min": 0.2,
        "y_max": 0.22,
        "char_start": 13,
        "char_end": 24,
        "words": [_word("Jean", 13, 0.1, 0.2, 0.2), _word("Pierre", 18, 0.25, 0.4, 0.2)],
    },
    {
        "text": "ocr",
        "x_min": 0.0,
        "x_max": 0.1,
        "y_min": 0.9,
        "y_max": 0.92,
        "char_start": None,
        "char_end": None,
        "words": [],
    },
]


def test_a_span_inside_one_line_gives_a_rectangle_tight_around_its_words() -> None:
    assert rects_for_span(LINES, 6, 12) == [{"x_min": 0.3, "y_min": 0.1, "x_max": 0.5, "y_max": 0.12}]


def test_a_span_over_two_lines_gives_one_rectangle_per_line() -> None:
    rects = rects_for_span(LINES, 6, 24)
    assert [round(r["y_min"], 2) for r in rects] == [0.1, 0.2]
    assert rects[1]["x_min"] == 0.1 and rects[1]["x_max"] == 0.4


def test_a_span_touching_one_word_only_does_not_take_its_neighbours() -> None:
    assert rects_for_span(LINES, 13, 17) == [{"x_min": 0.1, "y_min": 0.2, "x_max": 0.2, "y_max": 0.22}]


def test_a_line_without_words_is_used_whole_and_lines_without_range_are_ignored() -> None:
    lines = [{**LINES[0], "words": []}, LINES[2]]
    assert rects_for_span(lines, 0, 5) == [{"x_min": 0.1, "y_min": 0.1, "x_max": 0.5, "y_max": 0.12}]


def test_no_text_boxes_or_no_overlap_gives_no_rectangle() -> None:
    assert rects_for_span([], 0, 5) == []
    assert rects_for_span(LINES, 30, 40) == []


def test_find_spans_prefers_the_exact_value_and_finds_every_occurrence() -> None:
    assert find_spans("Paris et Paris", "Paris") == [(0, 5), (9, 14)]


def test_find_spans_ignores_case_and_whitespace_shape_when_the_llm_reformatted() -> None:
    assert find_spans("12 rue\ndes Lilas", "12 RUE des lilas") == [(0, 16)]


def test_find_spans_gives_nothing_for_an_empty_or_absent_value() -> None:
    assert find_spans("Dupont", "") == []
    assert find_spans("Dupont", "Durand") == []
    assert find_spans("", "Dupont") == []


def test_find_spans_caps_a_very_common_value() -> None:
    assert len(find_spans("a " * 50, "a")) == 10
