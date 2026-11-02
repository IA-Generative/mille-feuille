"""Les pages du dossier et les sources de la base de connaissances partagent une seule suite de numéros."""

import pytest

from app.agent.source_numbering import SourceNumbering
from app.agent.tools import AgentTools, SearchHit

pytestmark = pytest.mark.anyio

DOSSIER = {
    "documents": [
        {
            "id": "doc-1",
            "name": "Statuts.pdf",
            "pages": [
                {"id": "pg-1", "page_number": 1, "content": "Les statuts de l'association Les Amis du quartier."},
                {"id": "pg-2", "page_number": 2, "content": "Article 3 : le RIB de l'association est joint."},
            ],
        }
    ],
    "execution_steps": [],
}


class _Found:
    """Une recherche qui trouve toujours la page 2."""

    async def search(self, query: str) -> list[SearchHit]:
        return [SearchHit("pg-2", 2, "doc-1", "Statuts.pdf", 0.5, "le RIB de l'association")]


async def test_a_page_read_or_found_keeps_one_number_for_the_whole_answer() -> None:
    tools = AgentTools(DOSSIER, searcher=_Found())

    read = tools.read_page(2)
    found = await tools.search_documents("RIB")
    reread = tools.read_page(2)

    assert read.startswith("[1] 📄 Page 2") and reread.startswith("[1] 📄 Page 2")
    assert "[1] 📄 Page 2" in found
    assert [(s.page_ids, s.number) for s in tools.consulted_sources()] == [(["pg-2"], 1)]


def test_each_new_page_takes_the_next_number() -> None:
    tools = AgentTools(DOSSIER)

    tools.read_page(2)
    tools.read_page(1)

    assert [s.number for s in tools.consulted_sources()] == [1, 2]


def test_the_numbers_are_shared_with_the_knowledge_base_of_the_same_answer() -> None:
    numbering = SourceNumbering()
    assert numbering.number("kb:x") == 1 and numbering.number("page:pg-1") == 2 and numbering.number("kb:x") == 1
