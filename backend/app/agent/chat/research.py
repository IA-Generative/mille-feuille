"""La recherche du chat : du code, sans appel au modèle. Les recherches du plan partent en parallèle, avec celle de la
question telle que la personne l'a écrite (lancée pendant que le plan se fait) ; les passages se fusionnent, du plus
pertinent au moins pertinent, et reçoivent leur numéro de source."""

import asyncio
import logging
from dataclasses import dataclass

from app.agent.tools import AgentTools, NotIndexedError, SearchHit

logger = logging.getLogger(__name__)

# Combien de passages le modèle lit : assez pour recouper, pas assez pour noyer sa réponse.
MAX_HITS = 8


@dataclass
class Evidence:
    """Ce que la recherche a trouvé, prêt à être donné au modèle."""

    text: str
    hits: int
    pages_read: int = 0

    @property
    def empty(self) -> bool:
        return self.hits == 0 and self.pages_read == 0


def merge(results: list[list[SearchHit]], limit: int = MAX_HITS) -> list[SearchHit]:
    """Les passages de toutes les recherches, le même passage une seule fois, les meilleurs d'abord."""
    best: dict[tuple[str, str], SearchHit] = {}
    for hits in results:
        for hit in hits:
            key = (hit.page_id, hit.excerpt)
            if key not in best or hit.score > best[key].score:
                best[key] = hit
    return sorted(best.values(), key=lambda hit: hit.score, reverse=True)[:limit]


async def search_all(tools: AgentTools, queries: list[str], speculative: asyncio.Task | None) -> list[SearchHit]:
    """Lève `NotIndexedError` si le dossier n'a pas d'index : l'appelant passe alors à la lecture de pages."""
    tasks = [asyncio.ensure_future(tools.search_hits(query)) for query in dict.fromkeys(queries)]
    if speculative is not None:
        tasks.append(speculative)
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)
    results: list[list[SearchHit]] = []
    failure: BaseException | None = None
    for outcome in outcomes:
        if isinstance(outcome, NotIndexedError):
            raise outcome
        if isinstance(outcome, BaseException):
            failure = outcome
            logger.warning("Une recherche du dossier a échoué", exc_info=outcome)
        else:
            results.append(outcome)
    if not results and failure is not None:
        raise failure
    return merge(results)


async def research(
    tools: AgentTools, queries: list[str], pages: list[int], speculative: asyncio.Task | None = None
) -> Evidence:
    """Les passages utiles à la réponse, numérotés. Vide si rien n'a été trouvé ; lève si la recherche est
    indisponible (dossier non indexé, index injoignable) pour que l'appelant se replie sur les outils."""
    hits = await search_all(tools, queries, speculative)
    parts = [tools.format_hits(hits)] if hits else []
    parts.extend(tools.read_page(number) for number in pages)
    return Evidence(text="\n\n".join(parts), hits=len(hits), pages_read=len(pages))
