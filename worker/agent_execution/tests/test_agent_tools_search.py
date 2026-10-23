"""Tests des outils de l'agent : recherche dans le dossier, lecture de page, classifications et entités."""

from app.search.retrieval import NotIndexedError, SearchHit
from app.tools import AgentTools


class FakeSearcher:
    """La recherche du dossier vue par les outils : des résultats donnés, ou une erreur."""

    def __init__(self, hits: list[SearchHit] | Exception | None = None) -> None:
        self.hits = hits if hits is not None else []
        self.queries: list[str] = []

    def search(self, query: str, top_k: int | None = None) -> list[SearchHit]:
        self.queries.append(query)
        if isinstance(self.hits, Exception):
            raise self.hits
        return self.hits


def hit(page_id: str = "page-1", number: int = 1, name: str = "CNI.pdf", excerpt: str = "Nom: Dupont", score=0.5):
    return SearchHit(page_id, number, "doc-1", name, score, excerpt)


def _make_dossier() -> dict:
    return {
        "id": "dossier-1",
        "documents": [
            {
                "id": "doc-1",
                "name": "CNI.pdf",
                "pages": [
                    {
                        "id": "page-1",
                        "page_number": 1,
                        "content": "Carte nationale d'identité. Nom: Dupont. Prénom: Jean.",
                        "screenshot_key": "screens/page-1.png",
                        "predictions": [
                            {
                                "kind": "label",
                                "name": "CNI",
                                "value": "CNI",
                                "confidence": 0.95,
                            },
                            {
                                "kind": "entity",
                                "name": "nom",
                                "value": "Dupont",
                                "confidence": 0.92,
                            },
                        ],
                    },
                ],
            },
            {
                "id": "doc-2",
                "name": "Justificatif.pdf",
                "pages": [
                    {
                        "id": "page-2",
                        "page_number": 2,
                        "content": "Facture d'électricité. Adresse: 123 rue de Paris.",
                        "screenshot_key": "screens/page-2.png",
                        "predictions": [
                            {
                                "kind": "label",
                                "name": "Facture",
                                "value": "Facture",
                                "confidence": 0.88,
                            },
                            {
                                "kind": "entity",
                                "name": "adresse",
                                "value": "123 rue de Paris",
                                "confidence": 0.85,
                            },
                        ],
                    },
                ],
            },
        ],
    }


# --- AgentTools tests ---


def test_tools_search_documents() -> None:
    searcher = FakeSearcher([hit(excerpt="Nom: Dupont. Prénom: Jean.")])
    result = AgentTools(_make_dossier(), searcher=searcher).search_documents("Dupont")

    assert searcher.queries == ["Dupont"]
    assert "page-1" not in result  # Should show page number, not ID
    assert "Page 1 (CNI.pdf)" in result
    assert "Dupont" in result and "[score: 0.50]" in result


def test_search_documents_numbers_the_page_found_and_records_it_as_a_source() -> None:
    tools = AgentTools(_make_dossier(), searcher=FakeSearcher([hit()]))
    result = tools.search_documents("Dupont")

    assert "[1] 📄 Page 1" in result
    source = tools.consulted_sources()[0]
    assert source.page_ids == ["page-1"] and source.number == 1 and "Dupont" in source.excerpt


def test_several_passages_of_one_page_share_one_number_and_one_result() -> None:
    hits = [hit(excerpt="Premier passage", score=0.9), hit(excerpt="Second passage", score=0.4), hit("page-2", 2)]
    tools = AgentTools(_make_dossier(), searcher=FakeSearcher(hits))

    result = tools.search_documents("x")

    assert result.startswith("2 résultat(s) trouvé(s)")
    assert "Premier passage […] Second passage" in result
    assert [s.page_ids for s in tools.consulted_sources()] == [["page-1"], ["page-2"]]


def test_search_documents_without_result() -> None:
    assert "Aucun résultat" in AgentTools(_make_dossier(), searcher=FakeSearcher([])).search_documents("zzz")


def test_search_documents_tells_the_model_when_the_dossier_is_not_indexed() -> None:
    tools = AgentTools(_make_dossier(), searcher=FakeSearcher(NotIndexedError("non indexé")))
    result = tools.search_documents("Dupont")
    assert "pas encore indexé" in result and "read_page" in result
    assert tools.consulted_sources() == []


def test_search_documents_survives_an_unavailable_index() -> None:
    tools = AgentTools(_make_dossier(), searcher=FakeSearcher(RuntimeError("qdrant injoignable")))
    result = tools.search_documents("Dupont")
    assert "indisponible" in result and "qdrant" not in result  # le détail technique reste dans les journaux


def test_search_documents_is_a_tool_the_model_can_call() -> None:
    tools = AgentTools(_make_dossier(), searcher=FakeSearcher([hit()]))
    assert "Dupont" in tools.dispatch_tool("search_documents", {"query": "Dupont"})


def test_tools_read_page() -> None:
    tools = AgentTools(_make_dossier())
    result = tools.read_page(1)
    assert "Page 1" in result
    assert "Carte nationale" in result


def test_tools_give_the_source_of_a_document_in_context() -> None:
    dossier = _make_dossier()
    dossier["documents"][0]["source"] = {"name": "Guichet", "description": "Remis en main propre"}
    tools = AgentTools(dossier, searcher=FakeSearcher([hit(name="CNI.pdf — source : Guichet")]))

    page = tools.read_page(1)
    assert "source : Guichet" in page
    assert "Source du document : Guichet — Remis en main propre" in page
    assert "source : Guichet" in tools.search_documents("Dupont")


def test_tools_without_source_keep_the_same_output() -> None:
    page = AgentTools(_make_dossier()).read_page(1)
    assert "Source du document" not in page
    assert "source :" not in page


def test_tools_read_page_not_found() -> None:
    tools = AgentTools(_make_dossier())
    result = tools.read_page(999)
    assert "introuvable" in result


def test_tools_view_classifications() -> None:
    tools = AgentTools(_make_dossier())
    result = tools.view_classifications()
    assert "CNI" in result
    assert "Facture" in result
    assert "Page 1" in result
    assert "Page 2" in result


def test_tools_view_entities() -> None:
    tools = AgentTools(_make_dossier())
    result = tools.view_entities()
    assert "nom" in result
    assert "Dupont" in result
    assert "adresse" in result
    assert "123 rue de Paris" in result


def test_tools_view_classifications_empty() -> None:
    dossier = _make_dossier()
    for doc in dossier["documents"]:
        for page in doc["pages"]:
            page["predictions"] = []
    tools = AgentTools(dossier)
    result = tools.view_classifications()
    assert "Aucune" in result


def test_tools_dispatch() -> None:
    tools = AgentTools(_make_dossier())
    result = tools.dispatch_tool("view_entities", {})
    assert "nom" in result


def test_tools_dispatch_unknown() -> None:
    tools = AgentTools(_make_dossier())
    result = tools.dispatch_tool("unknown_tool", {})
    assert "inconnu" in result


def test_tools_tool_definitions() -> None:
    tools = AgentTools(_make_dossier())
    defs = tools.tool_definitions()
    names = [d["function"]["name"] for d in defs]
    assert "search_documents" in names
    assert "read_page" in names
    assert "view_classifications" in names
    assert "view_entities" in names


# --- Passage de relais vers l'assistant ---


def test_tools_suggest_assistant_memorizes_question() -> None:
    tools = AgentTools(_make_dossier())
    assert tools.assistant_question() is None
    result = tools.dispatch_tool("suggest_assistant", {"question": " Crée une analyse CNI "})
    assert "assistant" in result
    assert tools.assistant_question() == "Crée une analyse CNI"


def test_assistant_suggestion_marker_encodes_question() -> None:
    from app.chat_graph import assistant_suggestion_marker

    marker = assistant_suggestion_marker("Crée une analyse -- CNI ?")
    assert marker.startswith("\n\n<!--assistant-suggestion:")
    assert marker.endswith("-->")
    assert "--" not in marker[len("\n\n<!--") : -len("-->")]
