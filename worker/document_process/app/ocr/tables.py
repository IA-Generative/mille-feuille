"""Les tableaux lus par le pod `table` sur une page scannée, écrits pour le texte de la page.

Le texte de la page reçoit chaque tableau en **Markdown** à sa place dans l'ordre de lecture (donc indexé et trouvé)
et, s'il est douteux, une ligne qui le dit. Une cellule qui couvre plusieurs lignes ou colonnes ne se dit pas en
Markdown : elle y a son texte à sa première place ; le HTML, lui, est exact et reste disponible sur `RenderedTable`."""

import html as html_lib
from dataclasses import dataclass, replace

from app.config import settings
from app.ocr.contracts import PageLayout, PageTables, TableStructure

# Un tableau plus gros que cela n'est pas gardé (la page retombe sur la lecture en texte) ; une cellule est coupée.
MAX_CELL_CHARS = 2000
MAX_MARKDOWN_CHARS = 900_000
MAX_HTML_CHARS = 1_800_000


@dataclass
class RenderedTable:
    """Un tableau de la page, prêt à être écrit dans son texte."""

    rank: int
    region_order: int
    n_rows: int
    n_cols: int
    has_header: bool
    headers: list[str] | None
    markdown: str
    html: str
    score: float
    reliable: bool
    model_version: str
    marker: str

    def described(self, description: str) -> "RenderedTable":
        """Le tableau avec sa description (le VLM du hub) sous lui."""
        return replace(self, marker=f"{self.marker}\n\n{description}")


def _text(value: str) -> str:
    """A cell's text on one line, within what the backend keeps."""
    return " ".join(value.split())[:MAX_CELL_CHARS]


def header_rows(table: TableStructure) -> int:
    """How many rows at the top are the header: one, or two when the first has a cell over several columns (a title
    above the names of the columns it groups)."""
    if not table.has_header:
        return 0
    first = [cell for cell in table.cells if cell.row == 0]
    return 2 if table.n_rows > 2 and any(cell.col_span > 1 for cell in first) else 1


def column_headers(table: TableStructure, rows: int) -> list[str]:
    """The header of each column: what the header rows say over it, from the top - "Résultats / Réalisé"."""
    headers = []
    for column in range(table.n_cols):
        parts: list[str] = []
        for cell in sorted(table.cells, key=lambda c: (c.row, c.col)):
            if cell.row < rows and cell.col <= column < cell.col + cell.col_span:
                text = _text(cell.text)
                if text and text not in parts:
                    parts.append(text)
        headers.append(" / ".join(parts))
    return headers


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|")


def to_markdown(table: TableStructure) -> str:
    """The grid as a Markdown table. A table with no header gets an empty one, which Markdown requires; a cell that
    spans several has its text in its first place and the others empty (the HTML is the exact one)."""
    grid = [["" for _ in range(table.n_cols)] for _ in range(table.n_rows)]
    for cell in table.cells:
        grid[cell.row][cell.col] = _text(cell.text)

    def row(texts: list[str]) -> str:
        return "| " + " | ".join(_escape(text) for text in texts) + " |"

    if table.has_header:
        header, body = grid[0], grid[1:]
    else:
        header, body = ["" for _ in range(table.n_cols)], grid
    return "\n".join([row(header), "| " + " | ".join("---" for _ in range(table.n_cols)) + " |", *map(row, body)])


def to_html(table: TableStructure) -> str:
    """The grid as an HTML table, spans said as they are. The first row is the head when it is a header."""

    def cell_html(cell, tag: str) -> str:
        spans = ""
        if cell.row_span > 1:
            spans += f' rowspan="{cell.row_span}"'
        if cell.col_span > 1:
            spans += f' colspan="{cell.col_span}"'
        return f"<{tag}{spans}>{html_lib.escape(_text(cell.text))}</{tag}>"

    rows: dict[int, list] = {}
    for cell in sorted(table.cells, key=lambda c: (c.row, c.col)):
        rows.setdefault(cell.row, []).append(cell)
    lines = ["<table>"]
    for index in range(table.n_rows):
        in_header = table.has_header and index == 0
        if in_header:
            lines.append("<thead>")
        elif table.has_header and index == 1:
            lines.append("<tbody>")
        elif not table.has_header and index == 0:
            lines.append("<tbody>")
        tag = "th" if in_header else "td"
        lines.append("<tr>" + "".join(cell_html(cell, tag) for cell in rows.get(index, [])) + "</tr>")
        if in_header:
            lines.append("</thead>")
    if table.n_rows > (1 if table.has_header else 0):
        lines.append("</tbody>")
    lines.append("</table>")
    return "\n".join(lines)


def marker(markdown: str, reliable: bool) -> str:
    """Ce que la page dit du tableau : sa grille en Markdown, et une ligne si sa structure est douteuse."""
    if reliable:
        return markdown
    return f"{markdown}\n\n[Structure du tableau douteuse]"


def render_page(layout: PageLayout, page_tables: PageTables) -> list[RenderedTable]:
    """Les tableaux d'une page, dans l'ordre de lecture, chacun avec son rang sur la page (dès 1). Refuse une page où
    un tableau trouvé par le layout n'a pas été lu : son contenu ne serait nulle part dans la page."""
    table_regions = sorted(region.reading_order for region in layout.regions if region.type.value == "table")
    read = {table.region_order: table for table in page_tables.tables}
    missing = [order for order in table_regions if order not in read]
    if missing:
        raise ValueError(f"the table pod read no table in region(s) {missing}")
    rendered = []
    for rank, order in enumerate(table_regions, start=1):
        table = read[order]
        rows = header_rows(table)
        headers = column_headers(table, rows) if rows else None
        reliable = table.score >= settings.OCR_TABLE_MIN_SCORE
        markdown, html = to_markdown(table), to_html(table)
        if len(markdown) > MAX_MARKDOWN_CHARS or len(html) > MAX_HTML_CHARS:
            raise ValueError(f"the table of region {order} is too big to be kept")
        rendered.append(
            RenderedTable(
                rank=rank,
                region_order=order,
                n_rows=table.n_rows,
                n_cols=table.n_cols,
                has_header=table.has_header,
                headers=headers,
                markdown=markdown,
                html=html,
                score=table.score,
                reliable=reliable,
                model_version=page_tables.model_version,
                marker=marker(markdown, reliable),
            )
        )
    return rendered
