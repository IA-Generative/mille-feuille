from liteparse import LiteParse
from liteparse.types import ParseResult

from app.config import settings


def parse_file(data: bytes) -> ParseResult:
    """Extrait le texte, les blocs de mise en page (avec bbox) et une
    capture par page d'un PDF/Office/image. OCR Tesseract (français par
    défaut) pour les pages scannées. Les bbox des blocs sont ce qu'une
    future étape de classification/extraction d'entités pourra référencer
    pour localiser sa réponse sur la page (voir prediction_bounding_boxes
    côté backend). `emit_word_boxes` ajoute une boîte par mot aux lignes de
    texte (`text_items`), d'où la localisation d'une valeur au mot près."""
    parser = LiteParse(
        output_format="json",
        ocr_enabled=True,
        ocr_language=settings.OCR_LANGUAGE,
        tessdata_path=settings.TESSDATA_PATH,
        extract_screenshots=True,
        extract_blocks=True,
        emit_word_boxes=True,
    )
    return parser.parse(data)
