"""Les morceaux de la réponse du chat, à mesure que le modèle les écrit.

Ils passent par un flux Redis (`chat:<conversation>:deltas`) et non par la base : un morceau toutes les quelques
dizaines de millisecondes ne mérite pas une ligne, et le flux SSE de n'importe quel pod les lit, que le travail tourne
sur ce pod ou sur un autre. Rien n'est gardé : le message final, lui, est en base, et c'est lui que le navigateur
recharge à la fin. Un morceau perdu n'est donc jamais une perte de réponse."""

import asyncio
import logging

import redis.asyncio as aioredis

from app.config import RedisSettings

logger = logging.getLogger(__name__)

STREAM_TTL_SECONDS = 300
STREAM_MAX_LEN = 5000

_clients: dict[int, aioredis.Redis] = {}


def _client() -> aioredis.Redis:
    """Un client par boucle d'événements : celui d'une boucle ne se partage pas avec une autre."""
    key = id(asyncio.get_running_loop())
    if key not in _clients:
        _clients[key] = aioredis.Redis.from_url(RedisSettings().REDIS_URL, decode_responses=True)
    return _clients[key]


def _key(conversation_id: str) -> str:
    return f"chat:{conversation_id}:deltas"


async def reset(conversation_id: str) -> None:
    """Une nouvelle réponse commence : les morceaux de la précédente ne regardent plus personne."""
    try:
        await _client().delete(_key(conversation_id))
    except Exception:
        logger.warning("Flux de réponse non remis à zéro", exc_info=True)


async def publish(conversation_id: str, text: str) -> None:
    """Meilleur effort : un flux injoignable ne doit jamais faire échouer la réponse."""
    try:
        client = _client()
        await client.xadd(_key(conversation_id), {"text": text}, maxlen=STREAM_MAX_LEN, approximate=True)
        await client.expire(_key(conversation_id), STREAM_TTL_SECONDS)
    except Exception:
        logger.warning("Morceau de réponse non publié", exc_info=True)


async def read(conversation_id: str, after: str, block_ms: int) -> list[tuple[str, str]]:
    """Les morceaux publiés après `after` (« 0 » pour tout lire), dans l'ordre : [(identifiant, texte)]. Attend jusqu'à
    `block_ms` qu'il en vienne — c'est ce qui réveille le flux SSE dès qu'un morceau arrive."""
    try:
        result = await _client().xread({_key(conversation_id): after}, block=block_ms, count=100)
    except Exception:
        logger.warning("Flux de réponse illisible", exc_info=True)
        await asyncio.sleep(block_ms / 1000)
        return []
    if not result:
        return []
    return [(entry_id, fields["text"]) for _stream, entries in result for entry_id, fields in entries]
