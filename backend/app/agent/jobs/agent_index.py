"""Tenir l'index des agents d'une analyse à jour (voir services/search/agent_index.py).

Un seul travail par analyse, relancé à chaque création ou changement de prompt d'un agent, et au démarrage : il compare
les agents à l'index et ne refait que la différence. Sans Qdrant ni modèle d'embeddings, il ne fait rien : le chat
donne alors tous les agents au plan."""

import asyncio
import logging
import uuid

from app.db import async_session_factory
from app.repositories.analyse_repository import AnalyseRepository
from app.services.search import agent_index

logger = logging.getLogger(__name__)


async def index_analyse_agents(analyse_id: str) -> None:
    if not agent_index.configured():
        return
    async with async_session_factory() as db:
        analyse = await AnalyseRepository(db).get(uuid.UUID(analyse_id))
        if analyse is None:
            return
        model = agent_index.embedding_model_of(analyse.search_settings)
        agents = [agent_index.IndexedAgent(str(a.id), a.name, a.prompt) for a in analyse.agents]
    if not model or not agents:
        return
    try:
        outcome = await asyncio.to_thread(agent_index.sync_analyse, analyse_id, agents, model)
    except Exception:
        logger.warning("Index des agents de l'analyse %s impossible", analyse_id, exc_info=True)
        return
    if outcome["indexed"] or outcome["removed"]:
        logger.info("Agents de l'analyse %s indexés : %s", analyse_id, outcome)
