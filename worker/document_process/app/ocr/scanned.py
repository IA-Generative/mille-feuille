"""Les pages scannées d'un fichier, lues par les pods d'OCR (OCR_ENGINE=layout) à la place du Tesseract de liteparse.

liteparse lit le fichier sans OCR et dit, page par page, si un OCR est nécessaire. Ces pages partent vers les pods -
leur layout (PP-DocLayoutV3), puis le texte de ses régions (PP-OCRv5), ses tableaux (SLANet_plus) et la description de
ses images (VLM du hub) - quelques-unes à la fois, et ce qui revient est assemblé en markdown de page et en lignes
positionnées (app/ocr/assemble.py). Une page qui ne peut pas être lue - un pod absent ou lent, une page sans région, une
où rien n'a été lu - retombe sur liteparse et Tesseract, et le fichier continue : il n'échoue que si celui-ci échoue
aussi.

La tâche qui appelle attend les pods (elle sonde leurs résultats, elle ne se bloque pas sur l'un d'eux). L'image
temporaire de chaque page est supprimée une fois les pages lues, quelle qu'en soit l'issue : un rejeu écrase ce qu'un
passage précédent a laissé."""

import dataclasses
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.config import settings
from app.ocr import assemble, describe, pages, routing
from app.ocr.contracts import PageDescriptions, PageLayout, PageTables, PageText, RegionToDescribe, RegionType
from app.ocr.tables import RenderedTable, render_page

logger = logging.getLogger(__name__)

# L'image d'une page au moins aussi proche que cela d'OCR_PAGE_DPI est lue telle quelle, sans refaire le rendu.
_DPI_TOLERANCE = 0.95


def is_scanned(page: Any) -> bool:
    """Si la lecture de liteparse ne suffit pas pour cette page : il la dit scannée ou son texte illisible ; ou il n'y a
    presque pas de texte natif et des images (une page blanche n'est pas un scan)."""
    stats = getattr(page, "complexity", None)
    if stats is None:
        # Sans les signaux de liteparse : aucun texte vaut un scan.
        return len((page.text or "").strip()) < settings.OCR_SCANNED_MIN_CHARS
    if stats.is_garbled or "scanned" in stats.reasons:
        return True
    has_images = stats.full_page_image or stats.has_substantial_images or stats.image_block_count > 0
    return stats.text_length < settings.OCR_SCANNED_MIN_CHARS and has_images


@dataclass
class ReadPage:
    """Une page lue par les pods : son markdown, ses lignes positionnées, et le layout avec lequel elle a été lue."""

    markdown: str
    items: list[Any]
    layout: PageLayout
    # Les tableaux lus comme tableaux, dans l'ordre de lecture. Vide quand ils ont été lus comme du texte.
    tables: list[RenderedTable] = field(default_factory=list)
    # Les descriptions de ses images et tableaux : ordre de lecture de la région -> (texte, modèle qui l'a écrit).
    captions: dict[int, tuple[str, str]] = field(default_factory=dict)


@dataclass
class _Job:
    page: Any
    image_key: str
    # "layout", then "read": the text of the regions, and the tables when there are some, both at once.
    stage: str = "layout"
    # The layout task's.
    result: Any = None
    # The read stage's tasks, by what they read: "ocr" and, when there are tables to read as tables, "table".
    reads: dict[str, Any] = field(default_factory=dict)
    deadline: float = 0.0
    layout: PageLayout | None = None
    # The regions that are tables read as text (OCR_READ_TABLES_AS_TEXT).
    tables: set[int] = field(default_factory=set)
    # What the read stage gave, while the descriptions are made.
    text: PageText | None = None
    rendered: list[RenderedTable] = field(default_factory=list)
    to_describe: list[RegionToDescribe] = field(default_factory=list)


class ScannedPageReader:
    """Sends pages to the pods and gathers what they answer. `app` is the Celery app that sends; `clock` and `sleep`
    are how a test makes time go."""

    def __init__(
        self,
        app: Any = None,
        storage: Any = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        captions: bool | None = None,
        caption_model: str | None = None,
    ) -> None:
        if app is None:
            from app.celery_app import celery_app as app
        if storage is None:
            from app.storage import storage
        self._app, self._storage, self._clock, self._sleep = app, storage, clock, sleep
        # Si les images sont décrites (pod `vision`) ; par défaut, ce que dit VISION_POD_ENABLED.
        self._captions = settings.VISION_POD_ENABLED if captions is None else captions
        # Le modèle du hub choisi par l'analyse du dossier ; à défaut CAPTION_MODEL, puis le VLM_MODEL du pod.
        self._caption_model = caption_model or settings.CAPTION_MODEL or None
        # Ce qui reste du plafond de descriptions du document.
        self._budget = settings.CAPTION_MAX_PER_DOCUMENT

    def read(
        self, document_id: str, scanned: list[Any], images: dict[int, bytes]
    ) -> tuple[dict[int, ReadPage], list[int]]:
        """Rend les pages lues (numéro -> ce qui en a été lu) et les numéros de celles qui ne l'ont pas été."""
        waiting = list(scanned)
        active: dict[int, _Job] = {}
        read: dict[int, ReadPage] = {}
        failed: list[int] = []
        window = max(settings.OCR_PAGE_WINDOW, 1)
        try:
            while waiting or active:
                while waiting and len(active) < window:
                    page = waiting.pop(0)
                    job = self._start(document_id, page, images.get(page.page_num))
                    if job is None:
                        failed.append(page.page_num)
                    else:
                        active[page.page_num] = job
                for number, job in list(active.items()):
                    outcome = self._poll(document_id, job)
                    if outcome is None:
                        continue
                    del active[number]
                    if isinstance(outcome, str):
                        logger.warning(f"Page {number} of {document_id} not read by the OCR pods: {outcome}")
                        failed.append(number)
                    else:
                        read[number] = outcome
                if active:
                    self._sleep(settings.OCR_POLL_SECONDS)
        except BaseException:
            # Ce qui a été envoyé n'est plus voulu (tâche interrompue, par exemple).
            for job in active.values():
                self._revoke(job)
            raise
        return read, failed

    def _start(self, document_id: str, page: Any, image: bytes | None) -> _Job | None:
        if not image:
            logger.warning(f"Page {page.page_num} of {document_id} has no image to send to the OCR pods")
            return None
        try:
            key = pages.put_page_image(self._storage, document_id, page.page_num, image)
            job = _Job(page=page, image_key=key)
            self._send_layout(document_id, job)
            return job
        except Exception as error:
            logger.warning(f"Page {page.page_num} of {document_id} could not be sent to the OCR pods: {error}")
            return None

    def _send_layout(self, document_id: str, job: _Job) -> None:
        job.result = self._app.send_task(routing.LAYOUT_PAGE_TASK, args=[document_id, job.page.page_num, job.image_key])
        job.deadline = self._clock() + settings.OCR_STAGE_TIMEOUT_SECONDS

    def _poll(self, document_id: str, job: _Job) -> ReadPage | str | None:
        """None: not yet. A string: why the page could not be read. Otherwise, the page read."""
        if self._clock() > job.deadline:
            self._revoke(job)
            if job.stage == "describe":
                # The page is read: it is kept without its descriptions.
                logger.warning(f"Descriptions of page {job.page.page_num} of {document_id} took too long, left out")
                return self._finalize(document_id, job, None)
            return f"the {job.stage} step took more than {settings.OCR_STAGE_TIMEOUT_SECONDS} s"
        pending = {"layout": job.result} if job.stage == "layout" else job.reads
        # Looked at once each: it is a request to Redis.
        ready = {name: result.ready() for name, result in pending.items()}
        for name, result in pending.items():
            # One that failed fails the page now: the others are no longer wanted.
            if ready[name] and not result.successful():
                reason = f"the {name} step failed: {result.result!r}"
                self._revoke(job)
                self._forget(job)
                if job.stage == "describe":
                    logger.warning(
                        f"Descriptions of page {job.page.page_num} of {document_id} failed, left out: {reason}"
                    )
                    return self._finalize(document_id, job, None)
                return reason
        if not all(ready.values()):
            return None
        stage = job.stage
        try:
            if stage == "layout":
                return self._on_layout(document_id, job)
            if stage == "describe":
                return self._on_described(document_id, job)
            return self._on_read(document_id, job)
        except (ValidationError, ValueError, TypeError) as error:
            self._forget(job)
            return f"the {stage} step answered something unexpected: {error}"

    def _on_layout(self, document_id: str, job: _Job) -> None | str:
        layout = PageLayout.model_validate(job.result.result)
        self._forget(job)
        if not layout.regions:
            return "no region found on the page"
        job.layout = layout
        as_text = settings.OCR_READ_TABLES_AS_TEXT
        regions_for_ocr, table_regions = [], []
        for region in layout.regions:
            if region.type is RegionType.TABLE:
                if as_text:
                    job.tables.add(region.reading_order)
                    region = region.model_copy(update={"type": RegionType.TEXT})
                else:
                    table_regions.append(region.model_dump(mode="json"))
            regions_for_ocr.append(region.model_dump(mode="json"))
        number = job.page.page_num
        # The text pod masks the tables it was not asked to read, so the two read their own parts of the page.
        job.reads = {
            "ocr": self._app.send_task(
                routing.OCR_REGIONS_TASK, args=[document_id, number, job.image_key, regions_for_ocr]
            )
        }
        if table_regions:
            job.reads["table"] = self._app.send_task(
                routing.TABLE_REGIONS_TASK, args=[document_id, number, job.image_key, table_regions]
            )
        job.stage = "read"
        job.result = None
        job.deadline = self._clock() + settings.OCR_STAGE_TIMEOUT_SECONDS
        return None

    def _on_read(self, document_id: str, job: _Job) -> ReadPage | str | None:
        assert job.layout is not None
        job.text = PageText.model_validate(job.reads["ocr"].result)
        job.rendered = []
        if "table" in job.reads:
            job.rendered = render_page(job.layout, PageTables.model_validate(job.reads["table"].result))
        self._forget(job)
        job.reads = {}
        job.to_describe = self._to_describe(job)
        if job.to_describe:
            try:
                self._send_descriptions(document_id, job)
                return None
            except Exception as error:
                logger.warning(f"Page {job.page.page_num} of {document_id}: descriptions not asked, left out: {error}")
        return self._finalize(document_id, job, None)

    def _to_describe(self, job: _Job) -> list[RegionToDescribe]:
        if not self._captions or job.layout is None:
            return []
        selected = describe.select_regions(job.layout, {table.region_order for table in job.rendered}, self._budget)
        self._budget -= len(selected)
        return selected

    def _send_descriptions(self, document_id: str, job: _Job) -> None:
        number = job.page.page_num
        regions_to_send = [region.model_dump(mode="json") for region in job.to_describe]
        model = self._caption_model
        job.reads = {
            "describe": self._app.send_task(
                routing.DESCRIBE_REGIONS_TASK,
                args=[document_id, number, job.image_key, regions_to_send, None, model],
            )
        }
        job.stage = "describe"
        job.deadline = self._clock() + settings.CAPTION_STAGE_TIMEOUT_SECONDS

    def _on_described(self, document_id: str, job: _Job) -> ReadPage | str:
        try:
            described = PageDescriptions.model_validate(job.reads["describe"].result)
        except (ValidationError, ValueError, TypeError) as error:
            logger.warning(f"Page {job.page.page_num} of {document_id}: descriptions unexpected, left out: {error}")
            described = None
        self._forget(job)
        return self._finalize(document_id, job, described)

    def _finalize(self, document_id: str, job: _Job, described: PageDescriptions | None) -> ReadPage | str:
        """Le markdown de la page, avec ses descriptions s'il y en a : `[Image : ...]` là où une image se trouve dans
        l'ordre de lecture, et sous un tableau."""
        assert job.layout is not None and job.text is not None
        asked = {region.id for region in job.to_describe}
        found = [
            item for item in (described.descriptions if described else []) if item.id in asked and item.text.strip()
        ]
        texts = [describe.clean(item.text) for item in found]
        captions = {
            item.id: (text, described.model_version)
            for item, text in zip(found, texts, strict=True)
            if text and described
        }
        rendered = [
            table.described(captions[table.region_order][0]) if table.region_order in captions else table
            for table in job.rendered
        ]
        markers = {table.region_order: table.marker for table in rendered}
        for order, (text, _) in captions.items():
            if order not in markers:
                markers[order] = describe.image_block(text)
        markdown, items = assemble.assemble(job.layout, job.text, job.page.width, job.page.height, job.tables, markers)
        if not markdown.strip():
            return "nothing was read on the page"
        return ReadPage(markdown, items, job.layout, rendered, captions)

    def _revoke(self, job: _Job) -> None:
        for result in [job.result, *job.reads.values()]:
            try:
                if result is not None and not result.ready():
                    result.revoke()
            except Exception as error:
                logger.debug(f"Could not revoke a {job.stage} task of page {job.page.page_num}: {error}")

    def _forget(self, job: _Job) -> None:
        for result in [job.result, *job.reads.values()]:
            try:
                if result is not None:
                    result.forget()
            except Exception as error:
                logger.debug(f"Could not forget a {job.stage} result of page {job.page.page_num}: {error}")


def _dpi(screenshot: Any, page: Any) -> float:
    return screenshot.width / (page.width / 72) if page.width else 0.0


def _images_for(data: bytes, scanned: list[Any], result: Any) -> dict[int, bytes]:
    """The image of each scanned page at OCR_PAGE_DPI: the screenshot liteparse already made when it is sharp enough,
    the page rendered again when it is not."""
    from app import parsing

    shots = {shot.page_num: shot for shot in getattr(result, "screenshots", None) or []}
    images: dict[int, bytes] = {}
    missing: list[int] = []
    for page in scanned:
        shot = shots.get(page.page_num)
        if shot is not None and _dpi(shot, page) >= settings.OCR_PAGE_DPI * _DPI_TOLERANCE:
            images[page.page_num] = shot.image_bytes
        else:
            missing.append(page.page_num)
    if missing:
        images.update({number: png for number, (png, _, _) in parsing.render_pages(data, missing).items()})
    return images


def read_scanned_pages(
    document_id: str,
    data: bytes,
    result: Any,
    reader: ScannedPageReader | None = None,
    caption_model: str | None = None,
) -> Any:
    """`result` (un ParseResult de liteparse) dont les pages scannées sont lues par les pods d'OCR. Inchangé - et rien
    n'est touché - quand OCR_ENGINE n'est pas "layout", ou qu'aucune page n'a besoin d'un OCR."""
    if settings.OCR_ENGINE != "layout":
        return result
    scanned = [page for page in result.pages if is_scanned(page)]
    if not scanned:
        return result
    from app import parsing
    from app.storage import storage

    numbers = [page.page_num for page in scanned]
    logger.info(
        f"{len(scanned)} of {len(result.pages)} page(s) need an OCR: read by the OCR pods, {pages_list(numbers)}"
    )
    started = time.monotonic()
    try:
        images = _images_for(data, scanned, result)
        reader = reader or ScannedPageReader(storage=storage, caption_model=caption_model)
        read, failed = reader.read(document_id, scanned, images)
    finally:
        try:
            pages.delete_pages_images(storage, document_id, numbers)
        except Exception as error:
            logger.warning(f"Could not drop the images sent to the OCR pods for {document_id}: {error}")

    replaced = {}
    for number, done in read.items():
        page = dataclasses.replace(
            next(page for page in scanned if page.page_num == number), text=done.markdown, text_items=done.items
        )
        replaced[number] = page
    if failed:
        logger.warning(
            f"{len(failed)} page(s) of {document_id} fall back on liteparse's own OCR: {pages_list(sorted(failed))}"
        )
        for page in parsing.tesseract_pages(data, failed).pages:
            replaced[page.page_num] = page
    logger.info(f"OCR pods: {len(read)} page(s) read, {len(failed)} fell back, in {time.monotonic() - started:.0f} s")
    return dataclasses.replace(result, pages=[replaced.get(page.page_num, page) for page in result.pages])


def pages_list(numbers: list[int]) -> str:
    """The pages as a short list for a log line: "1-3, 7"."""
    from app.parsing import _page_list

    return _page_list(numbers).replace(",", ", ")
