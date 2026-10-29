"""Un modèle du hub qui lit les images (tout VLM compatible OpenAI) décrit les régions d'une page.

Chaque région est recadrée dans la page et montrée au modèle (`/chat/completions` du hub, comme
worker/classification) : la description revient avec les jetons consommés."""

import base64
import io
import time

import httpx
from PIL import Image

from app.config import settings
from app.contracts import DescribeUsage, PageDescriptions, RegionDescription, RegionToDescribe

IMAGE_PROMPT = (
    "Décris cette image en une ou deux phrases, en français, de façon factuelle : ce qu'elle montre, et le texte "
    "lisible qu'elle contient. Réponds par la description seule."
)
TABLE_PROMPT = (
    "Décris ce tableau en une ou deux phrases, en français : son sujet, ses colonnes, ce qu'il permet de savoir. "
    "Ne recopie pas ses cellules. Réponds par la description seule."
)


def _png_data_url(image: Image.Image) -> str:
    out = io.BytesIO()
    image.convert("RGB").save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


def crop(page: Image.Image, region: RegionToDescribe, margin: int) -> Image.Image:
    """La région de la page, avec une marge, coupée au bord de la page."""
    width, height = page.size
    box = region.box
    left, right = max(round(box.x_min * width) - margin, 0), min(round(box.x_max * width) + margin, width)
    top, bottom = max(round(box.y_min * height) - margin, 0), min(round(box.y_max * height) + margin, height)
    return page.crop((left, top, max(right, left + 1), max(bottom, top + 1)))


class HubDescriber:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            base_url=settings.OPENAI_API_BASE_URL.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            timeout=settings.HUB_TIMEOUT_SECONDS,
        )

    def describe(
        self,
        page_png: bytes,
        regions: list[RegionToDescribe],
        document_id: str,
        page_number: int,
        model: str,
        prompt: str | None = None,
    ) -> PageDescriptions:
        """`prompt` remplace la question posée pour chaque région ; sans lui, une pour une image, une pour un
        tableau."""
        if len(regions) > settings.VISION_MAX_REGIONS:
            raise ValueError(f"{len(regions)} regions to describe, over the {settings.VISION_MAX_REGIONS} of a page")
        started = time.monotonic()
        found: list[RegionDescription] = []
        prompt_tokens = completion_tokens = 0
        counted = False
        with Image.open(io.BytesIO(page_png)) as page:
            for region in regions:
                question = prompt or (TABLE_PROMPT if region.kind == "table" else IMAGE_PROMPT)
                url = _png_data_url(crop(page, region, settings.VISION_CROP_MARGIN_PIXELS))
                response = self._client.post(
                    "/chat/completions",
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": question},
                                    {"type": "image_url", "image_url": {"url": url}},
                                ],
                            }
                        ],
                        "max_tokens": settings.HUB_MAX_TOKENS,
                    },
                )
                response.raise_for_status()
                answer = response.json()
                usage = answer.get("usage") or {}
                if usage.get("prompt_tokens") is not None:
                    counted = True
                    prompt_tokens += usage["prompt_tokens"]
                    completion_tokens += usage.get("completion_tokens") or 0
                content = (answer["choices"][0]["message"].get("content") or "").strip()
                if content:
                    found.append(RegionDescription(id=region.id, text=content))
        return PageDescriptions(
            document_id=document_id,
            page_number=page_number,
            descriptions=found,
            model_version=model,
            usage=DescribeUsage(
                model=model,
                prompt_tokens=prompt_tokens if counted else None,
                completion_tokens=completion_tokens if counted else None,
                seconds=round(time.monotonic() - started, 3),
            ),
        )


_hub: HubDescriber | None = None


def get_hub_describer() -> HubDescriber:
    """Construit à la première utilisation : le client n'existe pas avant qu'une tâche en ait besoin."""
    global _hub
    if _hub is None:
        _hub = HubDescriber()
    return _hub
