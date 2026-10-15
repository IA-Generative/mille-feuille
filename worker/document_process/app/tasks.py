"""Tâche d'entrée du pipeline document_process : extraction de texte.

Télécharge le document depuis S3, en extrait le texte, les bbox des blocs
de mise en page et une capture par page (liteparse), puis écrit chaque page
côté backend. Pas de NER/relations ici (issue #4, prochaine étape) - juste
le texte et sa localisation, comme convenu. Le statut d'extraction du
document (en_attente -> en_cours -> terminé/échec) est reporté au backend à
chaque étape, pour que le frontend puisse le suivre.
"""

import hashlib
import logging

from liteparse.types import AnnotationRect, ParsedPage, TextItem, WordBox

from app import api_client
from app.celery_app import celery_app
from app.parsing import parse_file
from app.storage import storage

logger = logging.getLogger(__name__)


def _normalize(
    bbox: AnnotationRect | TextItem | WordBox, page_width: float, page_height: float
) -> tuple[float, float, float, float] | None:
    """Pixels -> 0-1 (origine en haut à gauche), et bornée à la page : liteparse
    peut renvoyer une bbox qui déborde légèrement (ex: interligne)."""
    if not page_width or not page_height:
        return None
    x_min = max(0.0, min(1.0, bbox.x / page_width))
    y_min = max(0.0, min(1.0, bbox.y / page_height))
    x_max = max(0.0, min(1.0, (bbox.x + bbox.width) / page_width))
    y_max = max(0.0, min(1.0, (bbox.y + bbox.height) / page_height))
    return x_min, y_min, x_max, y_max


def _box(item, page: ParsedPage) -> dict | None:
    """Coordonnées normalisées (0-1) d'une ligne ou d'un mot, au format de l'API ; None si la page n'a pas de taille."""
    normalized = _normalize(item, page.width, page.height)
    if normalized is None:
        return None
    x_min, y_min, x_max, y_max = normalized
    return {"x_min": x_min, "y_min": y_min, "x_max": x_max, "y_max": y_max}


def _locate(text: str, haystack: str, cursor: int) -> tuple[int | None, int]:
    """Position de `text` dans `haystack` à partir de `cursor` : (début ou None, nouveau curseur). Le curseur ne recule
    jamais, pour que deux occurrences identiques (« 12 » deux fois) soient chacune attribuée à la bonne."""
    start = haystack.find(text, cursor)
    if start == -1:
        return None, cursor
    return start, start + len(text)


def build_text_boxes(page: ParsedPage) -> list[dict]:
    """Texte positionné de la page : une entrée par ligne (`text_items`), avec ses mots. Les intervalles de caractères
    sont relatifs à `page.text` ; ils valent None quand le fragment n'y est pas retrouvé (OCR)."""
    boxes = []
    cursor = 0
    for item in page.text_items:
        box = _box(item, page)
        if not item.text or box is None:
            continue
        start, cursor = _locate(item.text, page.text, cursor)
        words = []
        word_cursor = 0
        for word in item.words:
            word_box = _box(word, page)
            if not word.text or word_box is None:
                continue
            word_start, word_cursor = _locate(word.text, item.text, word_cursor)
            absolute = start + word_start if start is not None and word_start is not None else None
            words.append(
                {
                    "text": word.text,
                    **word_box,
                    "char_start": absolute,
                    "char_end": absolute + len(word.text) if absolute is not None else None,
                }
            )
        boxes.append(
            {
                "text": item.text,
                **box,
                "char_start": start,
                "char_end": start + len(item.text) if start is not None else None,
                "words": words,
            }
        )
    return boxes


@celery_app.task(name="app.tasks.extract_document_text", bind=True)
def extract_document_text(self, document_id: str) -> None:
    with api_client.get_client() as client:
        api_client.set_extraction_status(client, document_id, status="en_cours")
        try:
            document = api_client.get_document(client, document_id)
            logger.info("Extracting text for document %s (%s)", document_id, document["name"])

            data = storage.get_object(document["s3_key"])

            # Hash SHA-256 du contenu du fichier (issue #52) : les bytes
            # sont déjà en mémoire, c'est le moment idéal pour le calculer.
            file_hash = hashlib.sha256(data).hexdigest()
            api_client.set_file_hash(client, document_id, file_hash=file_hash)

            result = parse_file(data)
            screenshots_by_page = {screenshot.page_num: screenshot for screenshot in result.screenshots}

            for page in result.pages:
                screenshot_key: str | None = None
                screenshot = screenshots_by_page.get(page.page_num)
                if screenshot is not None:
                    screenshot_key = f"screenshots/{document_id}/page-{page.page_num}.png"
                    storage.put_object(screenshot_key, screenshot.image_bytes, content_type="image/png")

                created_page = api_client.add_page(
                    client, document_id, page_number=page.page_num, content=page.text, screenshot_key=screenshot_key
                )

                bbox_count = 0
                for block in page.blocks or []:
                    if not block.text or block.bbox is None:
                        continue
                    normalized = _normalize(block.bbox, page.width, page.height)
                    if normalized is None:
                        continue
                    x_min, y_min, x_max, y_max = normalized
                    api_client.add_bounding_box(
                        client, created_page["id"], x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max
                    )
                    bbox_count += 1

                text_boxes = build_text_boxes(page)
                if text_boxes:
                    api_client.replace_text_boxes(client, created_page["id"], text_boxes)

                logger.info("Page %d: %d bbox(es), %d ligne(s) de texte", page.page_num, bbox_count, len(text_boxes))

            logger.info("Extracted %d page(s) for document %s", len(result.pages), document_id)
        except Exception as error:
            logger.exception("Text extraction failed for document %s", document_id)
            api_client.set_extraction_status(client, document_id, status="échec", error=str(error))
            raise
        else:
            api_client.set_extraction_status(client, document_id, status="terminé")
            # Déclenche la génération du résumé du document (issue #52) :
            # le texte des pages est maintenant disponible, on l'envoie sur
            # la file agent_execution pour que le LLM le résume.
            dossier_id = document.get("dossier_id")
            if dossier_id:
                celery_app.send_task(
                    "app.tasks.run_document_summary",
                    args=[str(dossier_id), document_id],
                    queue="agent_execution",
                )
