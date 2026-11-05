"""Les noms des modèles que le hub LLM sert. Seuls les noms sont lus : ce que chaque modèle sait faire, c'est
l'administrateur qui le dit (voir `app/models/llm_model.py`). La lecture est gardée (Redis) jusqu'à ce qu'on la
relance : la liste des modèles enregistrés sert de mémoire, le hub n'est interrogé que sur demande."""

import json
from datetime import UTC, datetime

from app.agent import llm
from app.connectors import redis_connector

_CACHE_KEY = "llm:hub_model_names"


async def read(*, refresh: bool = False) -> tuple[list[str], datetime]:
    """(noms, date de la lecture). Interroge le hub si `refresh` ou si rien n'a encore été lu."""
    if not refresh:
        cached = redis_connector.client.get(_CACHE_KEY)
        if cached is not None:
            data = json.loads(cached)
            return data["names"], datetime.fromisoformat(data["read_at"])
    available = await llm.client().models.list()
    names = sorted({model.id for model in available.data})
    read_at = datetime.now(UTC)
    redis_connector.client.set(_CACHE_KEY, json.dumps({"names": names, "read_at": read_at.isoformat()}))
    return names, read_at
