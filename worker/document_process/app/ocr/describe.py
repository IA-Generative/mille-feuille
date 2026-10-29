"""La description des images et des tableaux d'une page scannée.

Quelles régions sont décrites (`select_regions`) et ce qui en est écrit : `[Image : ...]` dans le texte de la page, à la
place de l'image dans l'ordre de lecture, et sous un tableau. La description est faite par le pod `vision` (un VLM du
hub) pendant que la page est lue : la page est écrite une fois, avec elle. Une description qui ne peut pas être faite
ne fait jamais échouer la page."""

import re

from app.config import settings
from app.ocr.contracts import (
    PageLayout,
    RegionToDescribe,
    RegionType,
)


def select_regions(layout: PageLayout, table_orders: set[int], budget: int) -> list[RegionToDescribe]:
    """Les régions à décrire : les images dont le petit côté fait au moins CAPTION_MIN_PIXELS, et les tableaux lus comme
    tableaux (`table_orders`) si CAPTION_TABLES ; les plus grandes d'abord quand il y en a plus que CAPTION_MAX_PER_PAGE
    ou que `budget` (ce qui reste du plafond du document). Dans l'ordre de lecture."""
    candidates: list[tuple[float, RegionToDescribe]] = []
    for region in layout.regions:
        is_table = region.type is RegionType.TABLE and region.reading_order in table_orders
        if not (region.type is RegionType.IMAGE or (is_table and settings.CAPTION_TABLES)):
            continue
        width = (region.box.x_max - region.box.x_min) * layout.width_px
        height = (region.box.y_max - region.box.y_min) * layout.height_px
        if min(width, height) < settings.CAPTION_MIN_PIXELS:
            continue
        candidates.append(
            (
                width * height,
                RegionToDescribe(id=region.reading_order, box=region.box, kind="table" if is_table else "image"),
            )
        )
    keep = max(min(settings.CAPTION_MAX_PER_PAGE, budget), 0)
    biggest = sorted(candidates, key=lambda item: item[0], reverse=True)[:keep]
    return sorted((region for _, region in biggest), key=lambda region: region.id)


def clean(text: str) -> str:
    """Une description propre au texte de la page : sur une ligne, sans crochet (ils ferment le bloc), coupée
    à un mot."""
    flat = re.sub(r"\s+", " ", text.replace("[", "(").replace("]", ")")).strip()
    if len(flat) > settings.CAPTION_MAX_CHARS:
        flat = flat[: settings.CAPTION_MAX_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return flat


def image_block(description: str) -> str:
    return f"[Image : {description}]"
