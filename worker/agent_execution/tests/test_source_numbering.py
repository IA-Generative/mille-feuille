"""Les pages du dossier et les sources de la base de connaissances partagent une seule suite de numéros."""

from app.source_numbering import SourceNumbering
from app.tools import AgentTools

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


def test_a_page_read_or_found_keeps_one_number_for_the_whole_answer() -> None:
    tools = AgentTools(DOSSIER)

    read = tools.read_page(2)
    found = tools.search_documents("RIB")
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


def test_the_prompt_asks_to_cite_by_number() -> None:
    from app import chat_graph

    prompt = chat_graph._build_system_prompt([], [])

    assert "numéro entre crochets" in prompt and "N'invente jamais un numéro" in prompt
