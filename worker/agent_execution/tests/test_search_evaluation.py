import json

import pytest
from qdrant_client import QdrantClient

from app.search import embeddings, evaluation, indexer, store
from app.search.evaluation import Case
from app.search.retrieval import DossierSearcher, SearchHit

SETTINGS = {
    "strategy": "classique",
    "chunk_model": None,
    "size": 200,
    "overlap": 20,
    "window": 0,
    "embedding_model": "m",
}


def hit(page=1, document="bail.pdf", excerpt="Le loyer est de 800 euros."):
    return SearchHit(f"p{page}", page, "d", document, 0.5, excerpt)


# --- Pertinence ---


def test_an_expectation_matches_on_document_page_and_text():
    assert evaluation.matches({"document": "bail", "page": 1}, hit())
    assert evaluation.matches({"contains": "800 EUROS"}, hit())
    assert evaluation.matches({"document": "bail.pdf", "page": 1, "contains": "loyer"}, hit())


def test_every_given_condition_must_hold():
    assert not evaluation.matches({"document": "autre.pdf", "page": 1}, hit())
    assert not evaluation.matches({"document": "bail.pdf", "page": 2}, hit())
    assert not evaluation.matches({"page": 1, "contains": "salaire"}, hit())


def test_an_empty_expectation_matches_nothing():
    assert not evaluation.matches({}, hit())


# --- Métriques ---


def test_recall_hit_and_mrr_of_a_case():
    case = Case("q", [{"page": 1}, {"page": 3}])
    hits = [hit(2), hit(1), hit(4)]
    recall, found, reciprocal = evaluation.score_case(case, hits, k=3)
    assert (recall, found, reciprocal) == (0.5, True, 0.5)


def test_results_after_k_do_not_count():
    case = Case("q", [{"page": 9}])
    assert evaluation.score_case(case, [hit(1), hit(2), hit(9)], k=2) == (0.0, False, 0.0)
    assert evaluation.score_case(case, [hit(1), hit(2), hit(9)], k=3)[2] == pytest.approx(1 / 3)


def test_a_case_without_any_result_scores_zero():
    assert evaluation.score_case(Case("q", [{"page": 1}]), [], k=5) == (0.0, False, 0.0)


# --- Jeu de questions ---


def test_load_cases():
    cases = evaluation.load_cases([{"question": "q ?", "expected": [{"page": 1}]}])
    assert cases == [Case("q ?", [{"page": 1}])]


@pytest.mark.parametrize(
    "raw", [{"question": "", "expected": [{"page": 1}]}, {"question": "q"}, {"question": "q", "expected": []}]
)
def test_a_case_needs_a_question_and_an_expectation(raw):
    with pytest.raises(ValueError):
        evaluation.load_cases([raw])


# --- De bout en bout, sur un vrai index ---

VOCAB = ["loyer", "salaire", "banque"]


@pytest.fixture
def searcher(monkeypatch):
    client = QdrantClient(":memory:")
    monkeypatch.setattr(store, "get_client", lambda: client)
    monkeypatch.setattr(
        embeddings,
        "embed_dense",
        lambda texts, model: [[t.lower().replace("bail", "loyer").count(w) + 0.01 for w in VOCAB] for t in texts],
    )
    pages = {
        "p1": "Le salaire net est de 2100 euros.",
        "p2": "Le loyer mensuel est de 800 euros.",
        "p3": "IBAN FR76 3000 6000 0112 3456 7890 189 ouvert à la banque.",
    }
    documents = [
        {"id": f"d{n}", "name": f"{pid}.pdf", "source": None, "pages": [{"id": pid, "page_number": 1, "content": text}]}
        for n, (pid, text) in enumerate(pages.items(), 1)
    ]
    name = store.collection_name("d1", "fp")
    indexer.reconcile(client, name, {"id": "d1", "documents": documents}, settings=SETTINGS, fingerprint="fp")
    store.swap_alias(client, "d1", name)
    return DossierSearcher("d1", qdrant=client, config={"index_settings": SETTINGS})


CASES = [
    Case("montant du bail", [{"document": "p2.pdf"}]),  # sens seul : aucun mot en commun avec le texte
    Case("FR76 3000 6000", [{"document": "p3.pdf"}]),  # mots exacts seuls : l'embedding jouet ne les connaît pas
]


def test_hybrid_finds_what_each_branch_alone_misses(searcher):
    results = evaluation.evaluate(searcher, CASES, k=1)

    assert results["lexical"].hit == 0.5  # trouve l'IBAN, pas le bail
    assert results["semantique"].hit >= 0.5
    assert results["hybride"].hit == 1.0 and results["hybride"].mrr == 1.0
    assert results["hybride"].hit >= max(results["lexical"].hit, results["semantique"].hit)


def test_the_report_lists_every_mode(searcher):
    report = evaluation.format_report(evaluation.evaluate(searcher, CASES, k=3), 3)
    assert [line.split()[0] for line in report.splitlines()] == ["mode", "lexical", "semantique", "hybride"]
    assert "recall@3" in report


def test_the_command_line_prints_the_report(searcher, tmp_path, monkeypatch, capsys):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{"question": "FR76 3000", "expected": [{"document": "p3.pdf"}]}]), encoding="utf-8")
    monkeypatch.setattr(evaluation, "DossierSearcher", lambda dossier_id: searcher)

    assert evaluation.main(["--dossier", "d1", "--cases", str(path), "--k", "2"]) == 0

    assert "hybride" in capsys.readouterr().out
