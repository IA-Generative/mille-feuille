"""Les lignes de la page qu'une source de message cite : de l'intervalle de caractères d'un passage trouvé aux zones à
entourer sur l'image de la page (une bbox par ligne)."""

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_page import BoundingBox, PageTextBox

# Au plus ce nombre de zones par source : une page entière citée ne doit pas devenir des centaines de bbox.
MAX_BOXES = 40


def lines_in(text_boxes: Iterable[PageTextBox], ranges: list[tuple[int, int]]) -> list[PageTextBox]:
    """Les lignes (dans l'ordre de lecture) dont l'intervalle de caractères recoupe un des passages. Une ligne sans
    intervalle (OCR : texte non retrouvé dans le contenu) ne peut pas être rattachée à un passage."""
    return [
        box
        for box in text_boxes
        if box.char_start is not None
        and box.char_end is not None
        and any(box.char_start < end and box.char_end > start for start, end in ranges)
    ][:MAX_BOXES]


async def attach_bounding_boxes(db: AsyncSession, sources: list[dict]) -> None:
    """Crée les bbox des sources qui citent des passages d'une seule page et en met les identifiants dans
    `bounding_box_ids`. Sans ligne positionnée (page sans texte positionné, OCR), la source reste sans bbox."""
    for source in sources:
        ranges = [(start, end) for start, end in source.get("char_ranges") or []]
        page_ids = source.get("page_ids") or []
        if not ranges or len(page_ids) != 1:
            continue
        page_id = uuid.UUID(str(page_ids[0]))
        rows = await db.scalars(
            select(PageTextBox).where(PageTextBox.document_page_id == page_id).order_by(PageTextBox.position)
        )
        boxes = [
            BoundingBox(
                document_page_id=page_id, x_min=line.x_min, y_min=line.y_min, x_max=line.x_max, y_max=line.y_max
            )
            for line in lines_in(rows, ranges)
        ]
        if not boxes:
            continue
        db.add_all(boxes)
        await db.flush()
        source["bounding_box_ids"] = [*(source.get("bounding_box_ids") or []), *(box.id for box in boxes)]
