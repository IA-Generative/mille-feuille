"""Le hub LLM : ses modèles et ce que chacun sait faire techniquement (son **type** : complétion, embeddings, audio,
image, vidéo). C'est le backend qui le lit, jamais l'administrateur qui le saisit.

- complétion et embeddings : un appel minimal au modèle, la seule façon fiable de le savoir (le standard OpenAI ne
  le dit pas) ;
- audio, image, vidéo : les métadonnées que le hub expose, quand il en expose (champ `mode`, `type`, `modalities`,
  `architecture.modality`…). Sans métadonnées, ces types ne sont pas déclarés : un modèle qui sait faire de l'audio sans
  que le hub le dise n'est pas reconnu comme tel.

La lecture (noms et types) est gardée dans Redis jusqu'à ce qu'on la relance : la liste des modèles enregistrés sert de
mémoire, le hub n'est interrogé que sur demande."""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.agent import llm
from app.connectors import redis_connector
from app.models.llm_model import LlmModelType

logger = logging.getLogger(__name__)

_CACHE_KEY = "llm:hub_models"
PROBE_TIMEOUT = 30
PROBE_CONCURRENCY = 8

# Les mots que les hubs emploient pour dire ce qu'un modèle fait, vers nos types.
_WORDS: dict[str, LlmModelType] = {
    "chat": LlmModelType.COMPLETION,
    "completion": LlmModelType.COMPLETION,
    "text": LlmModelType.COMPLETION,
    "embedding": LlmModelType.EMBEDDING,
    "embeddings": LlmModelType.EMBEDDING,
    "audio": LlmModelType.AUDIO,
    "audio_transcription": LlmModelType.AUDIO,
    "audio_speech": LlmModelType.AUDIO,
    "transcription": LlmModelType.AUDIO,
    "speech": LlmModelType.AUDIO,
    "tts": LlmModelType.AUDIO,
    "stt": LlmModelType.AUDIO,
    "image": LlmModelType.IMAGE,
    "image_generation": LlmModelType.IMAGE,
    "vision": LlmModelType.IMAGE,
    "video": LlmModelType.VIDEO,
    "video_generation": LlmModelType.VIDEO,
}
# Seuls ceux que les sondes ne couvrent pas se lisent dans les métadonnées.
_FROM_METADATA = {LlmModelType.AUDIO, LlmModelType.IMAGE, LlmModelType.VIDEO}


@dataclass(frozen=True)
class HubModel:
    name: str
    types: list[str]


def _words(value: Any) -> list[str]:
    """Les mots d'un champ de métadonnées : une chaîne (« text+image->text »), une liste, ou rien."""
    if isinstance(value, str):
        return [word for word in value.lower().replace("->", " ").replace("+", " ").replace(",", " ").split() if word]
    if isinstance(value, list):
        return [word for item in value for word in _words(item)]
    return []


def types_from_metadata(extra: dict[str, Any]) -> set[LlmModelType]:
    """Audio, image et vidéo d'après ce que le hub dit du modèle ; vide s'il n'en dit rien."""
    found: set[LlmModelType] = set()
    architecture = extra.get("architecture")
    fields = [extra.get(key) for key in ("mode", "type", "model_type", "modality", "modalities")]
    fields += [extra.get("input_modalities"), extra.get("output_modalities"), extra.get("capabilities")]
    if isinstance(architecture, dict):
        fields.append(architecture.get("modality"))
    for field in fields:
        if isinstance(field, dict):  # {"audio": true, "vision": false}
            field = [key for key, enabled in field.items() if enabled]
        for word in _words(field):
            kind = _WORDS.get(word)
            if kind in _FROM_METADATA:
                found.add(kind)
    return found


async def _supports_completion(model_id: str) -> bool:
    try:
        await llm.client().chat.completions.create(
            model=model_id, messages=[{"role": "user", "content": "ping"}], max_tokens=1, timeout=PROBE_TIMEOUT
        )
        return True
    except Exception:
        return False


async def _supports_embedding(model_id: str) -> bool:
    try:
        await llm.client().embeddings.create(model=model_id, input="ping", timeout=PROBE_TIMEOUT)
        return True
    except Exception:
        return False


async def _detect(model_id: str, extra: dict[str, Any], gate: asyncio.Semaphore) -> HubModel:
    async with gate:
        completion, embedding = await asyncio.gather(_supports_completion(model_id), _supports_embedding(model_id))
    types: set[LlmModelType] = types_from_metadata(extra)
    if completion:
        types.add(LlmModelType.COMPLETION)
    if embedding:
        types.add(LlmModelType.EMBEDDING)
    return HubModel(model_id, sorted(kind.value for kind in types))


async def read(*, refresh: bool = False) -> tuple[list[HubModel], datetime]:
    """(modèles avec leurs types, date de la lecture). Interroge le hub (et sonde chaque modèle) si `refresh` ou si rien
    n'a encore été lu."""
    if not refresh:
        cached = redis_connector.client.get(_CACHE_KEY)
        if cached is not None:
            data = json.loads(cached)
            return [HubModel(**item) for item in data["models"]], datetime.fromisoformat(data["read_at"])
    available = await llm.client().models.list()
    gate = asyncio.Semaphore(PROBE_CONCURRENCY)
    models = sorted(
        await asyncio.gather(*(_detect(model.id, model.model_extra or {}, gate) for model in available.data)),
        key=lambda model: model.name,
    )
    read_at = datetime.now(UTC)
    redis_connector.client.set(
        _CACHE_KEY,
        json.dumps(
            {"models": [{"name": model.name, "types": model.types} for model in models], "read_at": read_at.isoformat()}
        ),
    )
    return models, read_at


def cached_types(name: str) -> list[str] | None:
    """Les types lus pour ce modèle à la dernière lecture du hub ; None si le hub n'a pas été lu ou l'ignore."""
    cached = redis_connector.client.get(_CACHE_KEY)
    if cached is None:
        return None
    return next((item["types"] for item in json.loads(cached)["models"] if item["name"] == name), None)
