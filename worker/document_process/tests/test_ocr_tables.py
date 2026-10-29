"""Les tableaux lus sur une page scannée : écrits en Markdown et HTML, et mis dans le texte de la page."""

import pytest

from app.config import settings
from app.ocr.contracts import (
    Box,
    PageLayout,
    PageTables,
    Region,
    RegionType,
    TableCell,
    TableStructure,
)
from app.ocr.tables import column_headers, header_rows, render_page, to_html, to_markdown

BOX = Box(x_min=0.1, y_min=0.1, x_max=0.5, y_max=0.2)


def _cell(row, col, text="", **spans) -> TableCell:
    return TableCell(row=row, col=col, text=text, **spans)


def _table(order=3, rows=3, cols=2, cells=None, header=True, score=0.95) -> TableStructure:
    cells = cells or [
        _cell(0, 0, "Année"),
        _cell(0, 1, "Dossiers"),
        _cell(1, 0, "2023"),
        _cell(1, 1, "1 120"),
        _cell(2, 0, "2024"),
        _cell(2, 1, "1 234"),
    ]
    return TableStructure(region_order=order, n_rows=rows, n_cols=cols, cells=cells, has_header=header, score=score)


def _layout(*types) -> PageLayout:
    regions = [Region(type=t, score=0.9, reading_order=i, box=BOX) for i, t in enumerate(types)]
    return PageLayout(document_id="d", page_number=3, width_px=100, height_px=100, regions=regions, model_version="l")


def _page_tables(*tables) -> PageTables:
    return PageTables(document_id="d", page_number=3, tables=list(tables), model_version="SLANet_plus_onnx")


# --- written out ---


def test_a_table_is_a_markdown_table_with_its_header():
    assert to_markdown(_table()) == ("| Année | Dossiers |\n| --- | --- |\n| 2023 | 1 120 |\n| 2024 | 1 234 |")


def test_a_table_without_header_gets_the_empty_one_that_markdown_requires():
    table = _table(header=False, rows=2, cells=[_cell(0, 0, "a"), _cell(0, 1, "b"), _cell(1, 0, "c"), _cell(1, 1, "d")])
    assert to_markdown(table) == "|  |  |\n| --- | --- |\n| a | b |\n| c | d |"


def test_what_would_break_a_markdown_row_is_escaped_or_flattened():
    table = _table(rows=1, header=False, cells=[_cell(0, 0, "a|b"), _cell(0, 1, "deux\nlignes  espacées")])
    assert to_markdown(table).splitlines()[2] == "| a\\|b | deux lignes espacées |"


def test_a_cell_that_spans_has_its_text_in_its_first_place_in_markdown_and_says_so_in_html():
    table = _table(
        rows=2,
        cells=[_cell(0, 0, "Résultats", col_span=2), _cell(1, 0, "a"), _cell(1, 1, "b")],
    )
    assert to_markdown(table).splitlines()[0] == "| Résultats |  |"
    html = to_html(table)
    assert '<th colspan="2">Résultats</th>' in html and "<td>a</td><td>b</td>" in html


def test_the_html_has_a_head_when_there_is_a_header_and_escapes_the_text():
    html = to_html(_table(rows=2, cells=[_cell(0, 0, "A<B"), _cell(0, 1, "x"), _cell(1, 0, "1 & 2"), _cell(1, 1, "y")]))
    assert html.splitlines() == [
        "<table>",
        "<thead>",
        "<tr><th>A&lt;B</th><th>x</th></tr>",
        "</thead>",
        "<tbody>",
        "<tr><td>1 &amp; 2</td><td>y</td></tr>",
        "</tbody>",
        "</table>",
    ]


def test_the_html_of_a_table_with_no_header_is_all_body():
    html = to_html(_table(rows=1, header=False, cells=[_cell(0, 0, "a"), _cell(0, 1, "b")]))
    assert "<thead>" not in html and html.count("<tr>") == 1 and "<tbody>" in html


def test_a_row_span_is_said_in_the_html():
    table = _table(rows=2, header=False, cells=[_cell(0, 0, "a", row_span=2), _cell(0, 1, "b"), _cell(1, 1, "c")])
    assert '<td rowspan="2">a</td>' in to_html(table)


# --- the headers ---


def test_a_header_is_one_row_and_a_merged_title_over_the_names_makes_two():
    assert header_rows(_table()) == 1
    assert header_rows(_table(header=False)) == 0
    merged = _table(
        rows=3,
        cols=2,
        cells=[
            _cell(0, 0, "Résultats", col_span=2),
            _cell(1, 0, "Réalisé"),
            _cell(1, 1, "Prévu"),
            _cell(2, 0, "1"),
            _cell(2, 1, "2"),
        ],
    )
    assert header_rows(merged) == 2
    assert column_headers(merged, 2) == ["Résultats / Réalisé", "Résultats / Prévu"]


def test_a_two_row_table_with_a_merged_first_row_keeps_one_header_row():
    """There would be nothing left under a second header row."""
    table = _table(rows=2, cells=[_cell(0, 0, "Titre", col_span=2), _cell(1, 0, "a"), _cell(1, 1, "b")])
    assert header_rows(table) == 1


def test_the_header_of_a_column_is_what_the_header_rows_say_over_it_once():
    assert column_headers(_table(), 1) == ["Année", "Dossiers"]
    assert column_headers(_table(), 0) == ["", ""]


# --- dans le texte de la page ---


def test_a_table_goes_in_the_page_as_its_markdown_grid():
    [table] = render_page(
        _layout(RegionType.TEXT, RegionType.TEXT, RegionType.TEXT, RegionType.TABLE), _page_tables(_table(3))
    )
    assert table.marker == to_markdown(_table(3))
    assert (table.rank, table.region_order, table.reliable, table.headers) == (1, 3, True, ["Année", "Dossiers"])


def test_a_table_without_header_has_no_headers():
    table = _table(
        0, header=False, rows=2, cells=[_cell(0, 0, "a"), _cell(0, 1, "b"), _cell(1, 0, "c"), _cell(1, 1, "d")]
    )
    [rendered] = render_page(_layout(RegionType.TABLE), _page_tables(table))
    assert rendered.headers is None


def test_the_ranks_follow_the_reading_order_not_the_order_the_pod_answered_in():
    layout = _layout(RegionType.TABLE, RegionType.TEXT, RegionType.TABLE)
    tables = render_page(layout, _page_tables(_table(2), _table(0)))
    assert [(t.rank, t.region_order) for t in tables] == [(1, 0), (2, 2)]


def test_a_doubtful_table_says_so_and_is_not_reliable(monkeypatch):
    monkeypatch.setattr(settings, "OCR_TABLE_MIN_SCORE", 0.6)
    [bad] = render_page(_layout(RegionType.TABLE), _page_tables(_table(0, score=0.49)))
    [good] = render_page(_layout(RegionType.TABLE), _page_tables(_table(0, score=0.6)))
    assert not bad.reliable and bad.marker.endswith("[Structure du tableau douteuse]")
    assert good.reliable and "douteuse" not in good.marker


def test_a_description_goes_under_the_table():
    [table] = render_page(_layout(RegionType.TABLE), _page_tables(_table(0)))
    assert table.described("les dossiers par année").marker == f"{to_markdown(_table(0))}\n\nles dossiers par année"


def test_a_table_the_layout_found_but_the_pod_did_not_read_refuses_the_page():
    """Its content would be in the page nowhere."""
    with pytest.raises(ValueError, match="no table in region"):
        render_page(_layout(RegionType.TABLE, RegionType.TABLE), _page_tables(_table(0)))


def test_a_table_too_big_to_be_kept_refuses_the_page(monkeypatch):
    monkeypatch.setattr("app.ocr.tables.MAX_MARKDOWN_CHARS", 10)
    with pytest.raises(ValueError, match="too big"):
        render_page(_layout(RegionType.TABLE), _page_tables(_table(0)))
