"""Les types d'un modèle (complétion, embeddings, audio, image, vidéo) lus par le backend sur le hub."""

from types import SimpleNamespace

import pytest

from app.models.llm_model import LlmModelType
from app.services import llm_hub, llm_models

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ({}, set()),
        ({"mode": "audio_transcription"}, {LlmModelType.AUDIO}),
        ({"mode": "image_generation"}, {LlmModelType.IMAGE}),
        ({"type": "video_generation"}, {LlmModelType.VIDEO}),
        ({"modalities": ["text", "image"]}, {LlmModelType.IMAGE}),
        ({"architecture": {"modality": "text+image+audio->text"}}, {LlmModelType.IMAGE, LlmModelType.AUDIO}),
        ({"capabilities": {"vision": True, "audio": False}}, {LlmModelType.IMAGE}),
        # La complétion et les embeddings se lisent par une sonde, pas dans les métadonnées.
        ({"mode": "chat"}, set()),
        ({"mode": "embedding"}, set()),
    ],
)
def test_audio_image_and_video_are_read_from_what_the_hub_says(extra: dict, expected: set) -> None:
    assert llm_hub.types_from_metadata(extra) == expected


async def test_completion_and_embeddings_come_from_probes_and_the_rest_from_metadata(monkeypatch) -> None:
    async def completion(model_id: str) -> bool:
        return model_id != "bge-m3"

    async def embedding(model_id: str) -> bool:
        return model_id == "bge-m3"

    monkeypatch.setattr(llm_hub, "_supports_completion", completion)
    monkeypatch.setattr(llm_hub, "_supports_embedding", embedding)
    import asyncio

    gate = asyncio.Semaphore(2)

    chat = await llm_hub._detect("mistral", {"modalities": ["text", "image"]}, gate)
    vectors = await llm_hub._detect("bge-m3", {}, gate)
    silent = await llm_hub._detect("whisper", {}, gate)

    assert chat.types == ["completion", "image"]
    assert vectors.types == ["embedding"]
    assert silent.types == ["completion"]  # le hub ne dit rien d'audio : pas déclaré


def test_a_model_with_unread_types_is_not_ruled_out_of_the_chat_selectors() -> None:
    def model(types):
        return SimpleNamespace(types=types)

    assert llm_models.can_complete(model(None))
    assert llm_models.can_complete(model(["completion", "image"]))
    assert not llm_models.can_complete(model(["embedding"]))
    assert not llm_models.can_complete(model(["audio"]))
