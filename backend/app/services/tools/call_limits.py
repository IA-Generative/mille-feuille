"""Quotas des appels de tools : par run (un run ne boucle pas sur un serveur) et par personne et par minute. Compteurs
dans Redis ; un dépassement renvoie le code `quota_depasse`, il ne lève rien."""

import asyncio

from redis import Redis

RUN_PREFIX = "millefeuille:tools:calls:run:"
MINUTE_PREFIX = "millefeuille:tools:calls:user:"
RUN_TTL_SECONDS = 3600
MINUTE_TTL_SECONDS = 60


class CallLimiter:
    def __init__(self, redis_client: Redis, *, per_run: int, per_minute: int) -> None:
        self._redis = redis_client
        self._per_run = per_run
        self._per_minute = per_minute

    def _count(self, key: str, ttl: int) -> int:
        count = self._redis.incr(key)
        if count == 1:
            self._redis.expire(key, ttl)
        return int(count)

    def _allow_sync(self, user_id: str, run_id: str | None) -> bool:
        if self._count(f"{MINUTE_PREFIX}{user_id}", MINUTE_TTL_SECONDS) > self._per_minute:
            return False
        return run_id is None or self._count(f"{RUN_PREFIX}{run_id}", RUN_TTL_SECONDS) <= self._per_run

    async def allow(self, user_id: str, run_id: str | None) -> bool:
        """Compte l'appel et dit s'il est dans les quotas."""
        return await asyncio.to_thread(self._allow_sync, user_id, run_id)
