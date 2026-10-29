"""Les images et tableaux d'une page scannée, décrits pendant qu'elle est lue : quelles régions, et ce que le texte
de la page en garde."""

import io

import pytest
from PIL import Image

from app.config import settings
from app.ocr import describe, routing
from app.ocr.contracts import (
    Box,
    DescribeUsage,
    PageDescriptions,
    PageLayout,
    Region,
    RegionDescription,
    RegionType,
)
from app.ocr.describe import select_regions
from app.ocr.scanned import ScannedPageReader
from tests.test_ocr_scanned import Clock, FakeApp, FakeResult, FakeStorage, _pages

BIG = Box(x_min=0.1, y_min=0.3, x_max=0.6, y_max=0.6)


def _png(width=1000, height=1000) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(out, format="PNG")
    return out.getvalue()


def _layout(*regions: Region) -> PageLayout:
    return PageLayout(
        document_id="d", page_number=1, width_px=1000, height_px=1000, regions=list(regions), model_version="l"
    )


def _image(order: int, box: Box = BIG, score: float = 0.9) -> Region:
    return Region(type=RegionType.IMAGE, score=score, reading_order=order, box=box)


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.setattr(settings, "CAPTION_MIN_PIXELS", 96)
    monkeypatch.setattr(settings, "CAPTION_MAX_PER_PAGE", 5)
    monkeypatch.setattr(settings, "CAPTION_MAX_PER_DOCUMENT", 50)
    monkeypatch.setattr(settings, "CAPTION_TABLES", True)
    monkeypatch.setattr(settings, "VISION_POD_ENABLED", True)
    monkeypatch.setattr(settings, "OCR_READ_TABLES_AS_TEXT", True)
    monkeypatch.setattr(settings, "CAPTION_MODEL", "")


# --- which regions ---


def test_only_the_images_big_enough_are_described():
    small = Box(x_min=0.1, y_min=0.1, x_max=0.15, y_max=0.5)
    selected = select_regions(_layout(_image(0, small), _image(1)), set(), budget=10)
    assert [region.id for region in selected] == [1]
    assert selected[0].kind == "image"


def test_the_biggest_win_when_a_page_has_more_than_its_cap_and_they_come_back_in_reading_order(monkeypatch):
    monkeypatch.setattr(settings, "CAPTION_MAX_PER_PAGE", 2)
    wide = Box(x_min=0.0, y_min=0.0, x_max=0.9, y_max=0.9)
    mid = Box(x_min=0.0, y_min=0.0, x_max=0.5, y_max=0.5)
    selected = select_regions(_layout(_image(0, mid), _image(1, BIG), _image(2, wide)), set(), budget=10)
    assert [region.id for region in selected] == [0, 2]


def test_what_is_left_of_the_documents_cap_bounds_a_page():
    assert len(select_regions(_layout(_image(0), _image(1)), set(), budget=1)) == 1
    assert select_regions(_layout(_image(0)), set(), budget=0) == []


def test_a_table_is_described_only_when_it_was_read_as_a_table():
    table = Region(type=RegionType.TABLE, score=0.9, reading_order=0, box=BIG)
    assert select_regions(_layout(table), set(), 10) == []
    assert [(r.id, r.kind) for r in select_regions(_layout(table), {0}, 10)] == [(0, "table")]


def test_the_tables_can_be_left_out(monkeypatch):
    monkeypatch.setattr(settings, "CAPTION_TABLES", False)
    table = Region(type=RegionType.TABLE, score=0.9, reading_order=0, box=BIG)
    assert select_regions(_layout(table), {0}, 10) == []


def test_a_description_is_one_line_without_brackets_and_cut_at_a_word(monkeypatch):
    monkeypatch.setattr(settings, "CAPTION_MAX_CHARS", 20)
    assert describe.clean("Un  [chat]\nnoir") == "Un (chat) noir"
    assert describe.clean("un très long texte sans fin") == "un très long texte…"


# --- through the reader ---


class VisionApp(FakeApp):
    """The pods, with the vision one."""

    def __init__(self, descriptions=None, ok=True):
        super().__init__()
        self.described = descriptions
        self.ok = ok

    def send_task(self, name, args):
        if name != routing.DESCRIBE_REGIONS_TASK:
            return super().send_task(name, args)
        self.sent.append((name, args))
        document_id, number, _, regions, prompt, model = args
        self.asked = {"prompt": prompt, "model": model}
        page = PageDescriptions(
            document_id=document_id,
            page_number=number,
            descriptions=[
                RegionDescription(id=r["id"], text=(self.described or {}).get(r["id"], "a bar chart")) for r in regions
            ],
            model_version=model or "pixtral",
            usage=DescribeUsage(model=model or "pixtral", seconds=1.5),
        )
        result = FakeResult(page.model_dump(mode="json") if self.ok else RuntimeError("pod down"), ok=self.ok)
        self.results.append(result)
        return result


def _reader(app, captions=True, clock=None):
    clock = clock or Clock()

    return ScannedPageReader(app=app, storage=FakeStorage(), clock=clock, sleep=clock.sleep, captions=captions)


def _read(app, captions=True, number=3):
    read, failed = _reader(app, captions).read("doc-1", _pages(number), {number: _png()})
    assert failed == []
    return read[number]


def test_the_images_go_to_the_vision_pod_and_the_page_says_what_they_show():
    app = VisionApp(descriptions={2: "Un histogramme des ventes."})

    page = _read(app)

    name, args = app.sent[-1]
    assert name == routing.DESCRIBE_REGIONS_TASK
    assert [region["id"] for region in args[3]] == [2]
    assert page.markdown == "# Titre 3\n\nUn paragraphe\n\n[Image : Un histogramme des ventes.]\n\nA B\n\n1 2"
    assert page.captions == {2: ("Un histogramme des ventes.", "pixtral")}
    # La description n'est pas du texte lu : pas de ligne positionnée pour elle.
    assert [item.text for item in page.items] == ["Titre 3", "Un paragraphe", "A B", "1 2"]


def test_a_table_read_as_a_table_gets_its_description_under_it(monkeypatch):
    monkeypatch.setattr(settings, "OCR_READ_TABLES_AS_TEXT", False)
    app = VisionApp(descriptions={2: "un histogramme", 3: "les ventes par année"})

    page = _read(app)

    assert [region["id"] for region in app.sent[-1][1][3]] == [2, 3]
    assert page.markdown.count("les ventes par année") == 1
    assert "[Image : un histogramme]" in page.markdown
    assert page.tables[0].marker.endswith("\n\nles ventes par année")
    assert page.captions[3] == ("les ventes par année", "pixtral")


def test_the_model_of_the_hub_is_the_one_asked_for_when_it_is_set(monkeypatch):
    monkeypatch.setattr(settings, "CAPTION_MODEL", "gpt-4o")
    app = VisionApp()
    page = _read(app)
    assert app.asked["model"] == "gpt-4o"
    assert page.captions[2][1] == "gpt-4o"


def test_the_pods_own_default_model_is_used_when_none_is_set(monkeypatch):
    monkeypatch.setattr(settings, "CAPTION_MODEL", "")
    app = VisionApp()
    _read(app)
    assert app.asked["model"] is None


def test_nothing_is_described_while_the_pod_is_not_deployed(monkeypatch):
    monkeypatch.setattr(settings, "VISION_POD_ENABLED", False)
    app = VisionApp()
    page = _read(app, captions=None)
    assert routing.DESCRIBE_REGIONS_TASK not in [name for name, _ in app.sent]
    assert "[Image" not in page.markdown and page.captions == {}


def test_a_pod_that_fails_leaves_the_page_without_descriptions_but_read():
    page = _read(VisionApp(ok=False))
    assert page.markdown == "# Titre 3\n\nUn paragraphe\n\nA B\n\n1 2"
    assert page.captions == {}


def test_a_pod_that_is_too_slow_leaves_the_page_without_descriptions_and_is_revoked(monkeypatch):
    monkeypatch.setattr(settings, "CAPTION_STAGE_TIMEOUT_SECONDS", 3)
    app = VisionApp()
    original = app.send_task

    def slow(name, args):
        result = original(name, args)
        if name == routing.DESCRIBE_REGIONS_TASK:
            result._after = 10_000
        return result

    app.send_task = slow
    page = _read(app)
    assert page.captions == {} and "[Image" not in page.markdown
    assert app.results[-1].revoked


def test_the_documents_cap_is_shared_by_its_pages(monkeypatch):
    monkeypatch.setattr(settings, "CAPTION_MAX_PER_DOCUMENT", 1)
    app = VisionApp()
    read, _ = _reader(app).read("doc-1", _pages(1, 2), {1: _png(), 2: _png()})
    assert len([name for name, _ in app.sent if name == routing.DESCRIBE_REGIONS_TASK]) == 1
    assert sum(1 for page in read.values() if page.captions) == 1
