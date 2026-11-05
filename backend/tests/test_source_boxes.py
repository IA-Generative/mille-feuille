"""Les lignes de la page qu'une source de message cite."""

from types import SimpleNamespace

from app.services.source_boxes import MAX_BOXES, lines_in


def line(start: int | None, end: int | None) -> SimpleNamespace:
    return SimpleNamespace(char_start=start, char_end=end)


def test_only_the_lines_that_overlap_a_passage_are_kept_in_reading_order() -> None:
    lines = [line(0, 10), line(11, 30), line(31, 50), line(51, 70)]

    assert lines_in(lines, [(25, 35)]) == [lines[1], lines[2]]
    assert lines_in(lines, [(0, 5), (60, 65)]) == [lines[0], lines[3]]


def test_a_passage_that_only_touches_a_line_does_not_select_it() -> None:
    lines = [line(0, 10), line(10, 20)]

    assert lines_in(lines, [(10, 15)]) == [lines[1]]


def test_lines_without_characters_are_ignored() -> None:
    assert lines_in([line(None, None), line(0, 10)], [(0, 100)]) == [line(0, 10)]


def test_a_whole_page_does_not_become_hundreds_of_boxes() -> None:
    lines = [line(i * 10, i * 10 + 9) for i in range(200)]

    assert len(lines_in(lines, [(0, 5000)])) == MAX_BOXES
