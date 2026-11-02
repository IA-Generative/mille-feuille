"""Les travaux de l'agent, lancés et suivis par le backend lui-même.

Un travail (agents d'une analyse, réponse du chat, résumé...) est une tâche de la boucle d'événements du backend, comme
une requête : il survit à la requête qui l'a créé, et l'état qu'il produit vit en base. Il n'y a plus de file Celery :

- un travail ne survit pas au redémarrage du pod qui l'exécute. Au démarrage, les travaux restés « en cours » sont
  déclarés en échec (`register_sweep`), pour que la personne le sache et relance au lieu d'attendre. Un travail
  vivant le dit dans Redis (battement toutes les `HEARTBEAT_EVERY` secondes) : un autre pod ne fait pas échouer ce
  qui tourne ailleurs ;
- le nombre de travaux menés en même temps par pod est borné (`MAX_CONCURRENT_JOBS`) : les autres attendent leur tour.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.config import AgentSettings
from app.connectors import redis_connector

logger = logging.getLogger(__name__)

settings = AgentSettings()

Job = Callable[[], Awaitable[None]]
# Un nettoyage reçoit `is_alive(nom)` : vrai si un pod (même un autre) exécute ce travail.
IsAlive = Callable[[str], Awaitable[bool]]
Sweep = Callable[[IsAlive], Awaitable[None]]

HEARTBEAT_EVERY = 20
HEARTBEAT_TTL = 60


def _beat_key(name: str) -> str:
    return f"agent:job:{name}"


class AgentRunner:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._slots: asyncio.Semaphore | None = None
        self._sweeps: list[Sweep] = []

    def register_sweep(self, sweep: Sweep) -> None:
        """`sweep` déclare en échec ce qu'un pod précédent a laissé « en cours » ; appelé au démarrage."""
        self._sweeps.append(sweep)

    async def start_up(self) -> None:
        self._slots = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)
        await self.fail_stale()

    async def fail_stale(self) -> None:
        for sweep in self._sweeps:
            try:
                await sweep(self.is_alive)
            except Exception:
                logger.exception("Le nettoyage des travaux interrompus a échoué")

    async def shut_down(self) -> None:
        """Les travaux en cours sont annulés ; ce qu'ils laissent « en cours » est repris par `fail_stale` au prochain
        démarrage."""
        running = list(self._tasks.values())
        for task in running:
            task.cancel()
        if running:
            await asyncio.gather(*running, return_exceptions=True)

    def start(self, name: str, job: Job) -> None:
        """Lance `job` en arrière-plan et rend la main aussitôt. `name` identifie le travail (un nom déjà en cours
        n'est pas relancé : un message redistribué ne double pas le travail)."""
        if name in self._tasks:
            logger.info("%s est déjà en cours, ignoré", name)
            return
        if self._slots is None:
            # Pas démarré par le lifespan de l'application (tests, scripts) : la même borne.
            self._slots = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)
        task = asyncio.create_task(self._run(name, job), name=name)
        self._tasks[name] = task
        task.add_done_callback(lambda _task: self._tasks.pop(name, None))

    def cancel(self, name: str) -> None:
        task = self._tasks.get(name)
        if task is not None:
            task.cancel()

    def is_running(self, name: str) -> bool:
        return name in self._tasks

    async def is_alive(self, name: str) -> bool:
        """Ce travail tourne-t-il quelque part ? Redis injoignable : oui, dans le doute on ne le fait pas échouer."""
        if name in self._tasks:
            return True
        try:
            return bool(await asyncio.to_thread(redis_connector.client.exists, _beat_key(name)))
        except Exception:
            logger.warning("Redis injoignable : %s supposé vivant", name, exc_info=True)
            return True

    async def is_alive_prefix(self, prefix: str) -> bool:
        """Un travail dont le nom commence ainsi tourne-t-il quelque part ? (Redis injoignable : oui, dans le doute.)"""
        if any(name.startswith(prefix) for name in self._tasks):
            return True
        try:
            keys = await asyncio.to_thread(
                lambda: list(redis_connector.client.scan_iter(match=f"{_beat_key(prefix)}*", count=100))
            )
            return bool(keys)
        except Exception:
            logger.warning("Redis injoignable : %s* supposé vivant", prefix, exc_info=True)
            return True

    async def _beat(self, name: str) -> None:
        while True:
            try:
                await asyncio.to_thread(redis_connector.client.set, _beat_key(name), 1, ex=HEARTBEAT_TTL)
            except Exception:
                logger.warning("Battement de %s impossible", name, exc_info=True)
            await asyncio.sleep(HEARTBEAT_EVERY)

    async def _run(self, name: str, job: Job) -> None:
        assert self._slots is not None
        async with self._slots:
            beat = asyncio.create_task(self._beat(name), name=f"{name}-beat")
            try:
                await job()
            except asyncio.CancelledError:
                logger.info("%s annulé", name)
                raise
            except Exception:
                # Chaque travail range son échec en base ; ici on ne fait que journaliser, sans relancer.
                logger.exception("%s a échoué", name)
            finally:
                beat.cancel()
                try:
                    await asyncio.to_thread(redis_connector.client.delete, _beat_key(name))
                except Exception:
                    logger.warning("Battement de %s non retiré", name, exc_info=True)


agent_runner = AgentRunner()
