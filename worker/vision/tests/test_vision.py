"""Le pod vision : le recadrage d'une région, les descriptions par id, et la tâche autour (le hub est un faux)."""

import io

import pytest
from PIL import Image

from app import tasks
from app.config import settings
from app.contracts import Box, PageDescriptions, RegionToDescribe
from app.hub import IMAGE_PROMPT, TABLE_PROMPT, HubDescriber, crop


def _png(width: int = 200, height: int = 100) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(out, format="PNG")
    return out.getvalue()


def _region(order: int, x0: float, y0: float, x1: float, y1: float, kind: str = "image") -> RegionToDescribe:
    return RegionToDescribe(id=order, box=Box(x_min=x0, y_min=y0, x_max=x1, y_max=y1), kind=kind)


class FakeHub:
    """`/chat/completions` du hub : répond à chaque appel et garde ce qu'on lui a demandé."""

    def __init__(self, content: str | None = None):
        self.calls: list[dict] = []
        self._content = content

    def post(self, url, json):
        self.calls.append({"url": url, **json})
        content = f"réponse {len(self.calls)}" if self._content is None else self._content

        class Response:
            def raise_for_status(self):
                pass

            def json(_self):
                return {
                    "choices": [{"message": {"content": content}}],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 10},
                }

        return Response()


def test_the_crop_is_the_region_and_its_margin_cut_at_the_edge_of_the_page():
    page = Image.new("RGB", (200, 100))
    assert crop(page, _region(0, 0.25, 0.5, 0.5, 1.0), 8).size == (50 + 16, 50 + 8)
    assert crop(page, _region(0, 0.0, 0.0, 0.0, 0.0), 0).size == (1, 1)


def test_the_hub_is_shown_each_crop_and_the_usage_is_added_up():
    hub = FakeHub()
    regions = [_region(1, 0, 0, 0.5, 0.5), _region(2, 0, 0, 1, 1, kind="table")]

    result = HubDescriber(hub).describe(_png(), regions, "doc", 3, "pixtral")

    assert [(d.id, d.text) for d in result.descriptions] == [(1, "réponse 1"), (2, "réponse 2")]
    assert result.model_version == "pixtral" and result.usage.model == "pixtral"
    assert (result.usage.prompt_tokens, result.usage.completion_tokens) == (100, 20)
    first = hub.calls[0]
    assert first["url"] == "/chat/completions" and first["model"] == "pixtral"
    assert first["messages"][0]["content"][0]["text"] == IMAGE_PROMPT
    assert first["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert hub.calls[1]["messages"][0]["content"][0]["text"] == TABLE_PROMPT


def test_a_prompt_replaces_the_question_for_every_region():
    hub = FakeHub()
    HubDescriber(hub).describe(_png(), [_region(1, 0, 0, 1, 1)], "doc", 1, "pixtral", prompt="Que vois-tu ?")
    assert hub.calls[0]["messages"][0]["content"][0]["text"] == "Que vois-tu ?"


def test_a_region_the_model_says_nothing_of_is_absent():
    result = HubDescriber(FakeHub(content="  ")).describe(_png(), [_region(1, 0, 0, 1, 1)], "doc", 1, "pixtral")
    assert result.descriptions == []


def test_a_page_with_too_many_regions_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "VISION_MAX_REGIONS", 1)
    with pytest.raises(ValueError):
        HubDescriber(FakeHub()).describe(_png(), [_region(0, 0, 0, 1, 1), _region(1, 0, 0, 1, 1)], "doc", 1, "x")


def test_the_task_reads_the_page_and_answers_a_contract(monkeypatch):
    hub = FakeHub(content="un chat")
    monkeypatch.setattr(tasks.storage, "get_object", lambda key: _png())
    monkeypatch.setattr(tasks, "get_hub_describer", lambda: HubDescriber(hub))
    box = {"x_min": 0, "y_min": 0, "x_max": 1, "y_max": 1}

    answer = tasks.describe_regions.run("doc", 4, "ocr-pages/doc/page-4.png", [{"id": 2, "box": box}])

    page = PageDescriptions.model_validate(answer)
    assert page.page_number == 4
    assert [(d.id, d.text) for d in page.descriptions] == [(2, "un chat")]
    assert hub.calls[0]["model"] == settings.VLM_MODEL


def test_the_task_uses_the_model_it_is_given(monkeypatch):
    hub = FakeHub(content="x")
    monkeypatch.setattr(tasks.storage, "get_object", lambda key: _png())
    monkeypatch.setattr(tasks, "get_hub_describer", lambda: HubDescriber(hub))
    box = {"x_min": 0, "y_min": 0, "x_max": 1, "y_max": 1}

    tasks.describe_regions.run("doc", 1, "k", [{"id": 0, "box": box}], "Décris", "gpt-4o")

    assert hub.calls[0]["model"] == "gpt-4o"
    assert hub.calls[0]["messages"][0]["content"][0]["text"] == "Décris"
