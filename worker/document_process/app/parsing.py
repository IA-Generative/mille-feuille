from liteparse import LiteParse
from liteparse.types import ParseResult

from app.config import settings


def _make_parser(**options) -> LiteParse:
    """Avec les pods d'OCR (OCR_ENGINE=layout), liteparse ne lance pas Tesseract lui-même - app/ocr/scanned.py envoie
    aux pods les pages dont il dit qu'elles ont besoin d'un OCR (`include_complexity`)."""
    return LiteParse(
        **{
            "output_format": "json",
            "ocr_enabled": settings.OCR_ENGINE == "tesseract",
            "include_complexity": settings.OCR_ENGINE == "layout",
            "ocr_language": settings.OCR_LANGUAGE,
            "tessdata_path": settings.TESSDATA_PATH,
            "extract_screenshots": True,
            "extract_blocks": True,
            # Les mots de chaque ligne, avec leur boîte : de quoi localiser une valeur au mot près.
            "emit_word_boxes": True,
            **options,
        }
    )


def parse_file(data: bytes) -> ParseResult:
    """Extrait le texte, les blocs de mise en page (avec bbox) et une
    capture par page d'un PDF/Office/image. OCR Tesseract (français par
    défaut) pour les pages scannées, ou pods PaddleOCR avec OCR_ENGINE=layout
    (voir app/ocr/scanned.py). Les bbox des blocs sont ce qu'une
    future étape de classification/extraction d'entités pourra référencer
    pour localiser sa réponse sur la page (voir prediction_bounding_boxes
    côté backend). `emit_word_boxes` ajoute une boîte par mot aux lignes de
    texte (`text_items`), d'où la localisation d'une valeur au mot près."""
    return _make_parser().parse(data)


def _page_list(page_numbers: list[int]) -> str:
    """Les pages comme `target_pages` de liteparse les écrit : "1,3-5"."""
    ordered = sorted(set(page_numbers))
    parts, start = [], 0
    while start < len(ordered):
        end = start
        while end + 1 < len(ordered) and ordered[end + 1] == ordered[end] + 1:
            end += 1
        parts.append(str(ordered[start]) if start == end else f"{ordered[start]}-{ordered[end]}")
        start = end + 1
    return ",".join(parts)


def render_pages(data: bytes, page_numbers: list[int]) -> dict[int, tuple[bytes, int, int]]:
    """L'image des pages demandées (PNG, largeur, hauteur) à OCR_PAGE_DPI - ce que lisent les pods d'OCR."""
    parser = _make_parser(
        ocr_enabled=False,
        include_complexity=False,
        extract_blocks=False,
        emit_word_boxes=False,
        dpi=settings.OCR_PAGE_DPI,
        target_pages=_page_list(page_numbers),
    )
    try:
        return {s.page_num: (s.image_bytes, s.width, s.height) for s in parser.parse(data).screenshots}
    finally:
        parser.close()


def tesseract_pages(data: bytes, page_numbers: list[int]) -> ParseResult:
    """Les pages demandées lues par l'OCR propre de liteparse - celles que les pods d'OCR n'ont pas su lire."""
    parser = _make_parser(ocr_enabled=True, include_complexity=False, target_pages=_page_list(page_numbers))
    try:
        return parser.parse(data)
    finally:
        parser.close()
