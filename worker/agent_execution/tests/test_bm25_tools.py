"""Tests pour la recherche BM25 et les outils de l'agent."""

from app.bm25 import BM25Index, _tokenize, build_index_from_dossier
from app.tools import AgentTools


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


# --- BM25 tests ---


def test_tokenize_basic() -> None:
    tokens = _tokenize("Hello World 123")
    assert tokens == ["hello", "world", "123"]


def test_tokenize_empty() -> None:
    assert _tokenize("") == []
    assert _tokenize(None) == []


def test_bm25_search_finds_relevant_page() -> None:
    index = build_index_from_dossier(_make_dossier())
    results = index.search("Dupont")
    assert len(results) > 0
    assert results[0].page_id == "page-1"
    assert "Dupont" in results[0].excerpt


def test_bm25_search_no_results() -> None:
    index = build_index_from_dossier(_make_dossier())
    results = index.search("zzznonexistent")
    assert results == []


def test_bm25_search_empty_index() -> None:
    index = BM25Index()
    index.build()
    assert index.search("test") == []


def test_bm25_search_empty_query() -> None:
    index = build_index_from_dossier(_make_dossier())
    assert index.search("") == []


# --- AgentTools tests ---


def test_tools_search_documents() -> None:
    tools = AgentTools(_make_dossier())
    result = tools.search_documents("Dupont")
    assert "page-1" not in result  # Should show page number, not ID
    assert "Page 1" in result
    assert "Dupont" in result


def test_tools_read_page() -> None:
    tools = AgentTools(_make_dossier())
    result = tools.read_page(1)
    assert "Page 1" in result
    assert "Carte nationale" in result


def test_tools_give_the_source_of_a_document_in_context() -> None:
    dossier = _make_dossier()
    dossier["documents"][0]["source"] = {"name": "Guichet", "description": "Remis en main propre"}
    tools = AgentTools(dossier)

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
