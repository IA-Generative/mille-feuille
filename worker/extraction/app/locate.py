"""Localisation d'une valeur extraite sur la page : de la valeur (ou de son span) aux rectangles à dessiner.

Les `text_boxes` d'une page (voir backend `PageTextBox`) donnent, pour chaque ligne et chaque mot, sa bbox normalisée
et son intervalle de caractères dans le contenu de la page. Une valeur dont on connaît le span (GLiNER) ou que l'on
retrouve dans le contenu (LLM) se traduit donc en un rectangle par ligne qu'elle couvre, serré autour de ses mots.
"""

import re

# Au-delà, une valeur très courante (« Paris ») noierait la page de rectangles sans rien apprendre de plus.
MAX_SPANS = 10


def find_spans(content: str, value: str, limit: int = MAX_SPANS) -> list[tuple[int, int]]:
    """Occurrences de `value` dans `content` : d'abord à l'identique, sinon sans tenir compte de la casse ni de la
    forme des espaces (le LLM reformate : un saut de ligne devient une espace, une casse change)."""
    value = value.strip()
    if not value or not content:
        return []
    spans = []
    start = content.find(value)
    while start != -1 and len(spans) < limit:
        spans.append((start, start + len(value)))
        start = content.find(value, start + len(value))
    if spans:
        return spans
    pattern = re.compile(r"\s+".join(re.escape(token) for token in value.split()), re.IGNORECASE)
    return [match.span() for match in pattern.finditer(content)][:limit]


def _overlaps(start: int | None, end: int | None, span_start: int, span_end: int) -> bool:
    return start is not None and end is not None and start < span_end and end > span_start


def _union(rects: list[dict]) -> dict:
    return {
        "x_min": min(r["x_min"] for r in rects),
        "y_min": min(r["y_min"] for r in rects),
        "x_max": max(r["x_max"] for r in rects),
        "y_max": max(r["y_max"] for r in rects),
    }


def rects_for_span(text_boxes: list[dict], span_start: int, span_end: int) -> list[dict]:
    """Un rectangle par ligne touchée par le span `[span_start, span_end)`, serré autour des mots qu'il recouvre (la
    ligne entière si elle n'a pas de mots détaillés). Les lignes sans intervalle (OCR) sont ignorées."""
    rects = []
    for box in text_boxes:
        if not _overlaps(box.get("char_start"), box.get("char_end"), span_start, span_end):
            continue
        words = [
            w for w in box.get("words") or [] if _overlaps(w.get("char_start"), w.get("char_end"), span_start, span_end)
        ]
        rects.append(_union(words or [box]))
    return rects
