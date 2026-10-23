"""Mesure de la qualité de la recherche dans un dossier : un jeu de questions de référence, des métriques de retrieval.

Un jeu de questions est un fichier JSON :

    [
      {"question": "Quel est le montant du loyer ?",
       "expected": [{"document": "bail.pdf", "page": 2}, {"contains": "800 euros"}]},
      ...
    ]

Un passage trouvé est **pertinent** s'il correspond à l'une des attentes : même document (par son nom) et même numéro de
page, et/ou texte contenu dans l'extrait. Les métriques :

- `recall@k` : part des attentes retrouvées parmi les k premiers résultats ;
- `hit@k` : part des questions qui ont au moins un résultat pertinent dans les k premiers ;
- `mrr` : moyenne de 1 / rang du premier résultat pertinent (0 s'il n'y en a pas).

On compare le **lexical seul** (ce que faisait l'ancien index BM25), le **sémantique seul** et l'**hybride**, sur les
mêmes questions. Pour comparer des stratégies de découpage ou des modèles d'embeddings, on indexe le même dossier
avec chaque réglage et on relance la mesure.

    uv run python -m app.search.evaluation --dossier <id> --cases questions.json --k 5"""

import argparse
import json
import sys
from dataclasses import dataclass, field

from app.search.retrieval import DossierSearcher, SearchHit

MODES = {"lexical": "sparse", "semantique": "dense", "hybride": "hybrid"}


@dataclass(frozen=True)
class Case:
    question: str
    expected: list[dict] = field(default_factory=list)


@dataclass
class Metrics:
    cases: int
    recall: float
    hit: float
    mrr: float


def load_cases(raw: list[dict]) -> list[Case]:
    cases = []
    for item in raw:
        if not item.get("question") or not item.get("expected"):
            raise ValueError("Chaque question demande un texte et au moins une attente")
        cases.append(Case(item["question"], list(item["expected"])))
    return cases


def matches(expectation: dict, hit: SearchHit) -> bool:
    """Le passage trouvé répond-il à cette attente ? Toutes les conditions données doivent tenir."""
    if "document" in expectation and expectation["document"].lower() not in hit.document_name.lower():
        return False
    if "page" in expectation and expectation["page"] != hit.page_number:
        return False
    if "contains" in expectation and expectation["contains"].lower() not in hit.excerpt.lower():
        return False
    return any(key in expectation for key in ("document", "page", "contains"))


def score_case(case: Case, hits: list[SearchHit], k: int) -> tuple[float, bool, float]:
    """(rappel, au moins un pertinent, rang réciproque) d'une question sur ses k premiers résultats."""
    top = hits[:k]
    found = sum(any(matches(e, hit) for hit in top) for e in case.expected)
    first = next((rank for rank, hit in enumerate(top, 1) if any(matches(e, hit) for e in case.expected)), None)
    return found / len(case.expected), first is not None, 1 / first if first else 0.0


def evaluate(searcher: DossierSearcher, cases: list[Case], *, k: int = 5) -> dict[str, Metrics]:
    """Les métriques de chaque mode (lexical, sémantique, hybride) sur les mêmes questions."""
    results: dict[str, Metrics] = {}
    for label, mode in MODES.items():
        scores = [score_case(case, searcher.search(case.question, top_k=k, mode=mode), k) for case in cases]
        n = len(cases) or 1
        results[label] = Metrics(
            cases=len(cases),
            recall=sum(s[0] for s in scores) / n,
            hit=sum(s[1] for s in scores) / n,
            mrr=sum(s[2] for s in scores) / n,
        )
    return results


def format_report(results: dict[str, Metrics], k: int) -> str:
    lines = [f"{'mode':<12} {'questions':>9} {f'recall@{k}':>10} {f'hit@{k}':>8} {'mrr':>6}"]
    for label, m in results.items():
        lines.append(f"{label:<12} {m.cases:>9} {m.recall:>10.2f} {m.hit:>8.2f} {m.mrr:>6.2f}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mesure du retrieval d'un dossier indexé")
    parser.add_argument("--dossier", required=True, help="Identifiant du dossier (déjà indexé)")
    parser.add_argument("--cases", required=True, help="Fichier JSON des questions de référence")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args(argv)
    with open(args.cases, encoding="utf-8") as file:
        cases = load_cases(json.load(file))
    print(format_report(evaluate(DossierSearcher(args.dossier), cases, k=args.k), args.k))
    return 0


if __name__ == "__main__":
    sys.exit(main())
