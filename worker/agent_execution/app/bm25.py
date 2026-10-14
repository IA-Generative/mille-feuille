"""Recherche BM25 locale sur le contenu des pages d'un dossier.

Contrairement à une recherche vectorielle (RAG classique), BM25 est
lexicale : il tokenise le texte et calcule un score de pertinence basé
sur la fréquence des termes. C'est suffisant pour des dossiers de
quelques dizaines de pages, sans infrastructure d'embedding.

L'index est construit en mémoire à partir des pages du dossier récupérées
via l'API interne. Il est jetable : reconstruit à chaque exécution d'agent.
"""

import logging
import re
from dataclasses import dataclass, field

from rank_bm25 import BM25Okapi

from app.config import settings

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    """Tokenisation simple : mots en minuscules. Suffisante pour le
    français et l'anglais sur des documents administratifs."""
    return [token.lower() for token in _WORD_RE.findall(text or "")]


@dataclass
class SearchResult:
    """Résultat de recherche BM25 : une page avec son score."""

    page_id: str
    page_number: int
    document_name: str
    score: float
    excerpt: str


@dataclass
class BM25Index:
    """Index BM25 jetable, construit à partir des pages d'un dossier.
    Chaque entrée pointe vers une page (id, numéro, nom du document)."""

    _tokens: list[list[str]] = field(default_factory=list)
    _metadata: list[dict] = field(default_factory=list)
    _bm25: BM25Okapi | None = None

    def add_page(self, page_id: str, page_number: int, document_name: str, content: str) -> None:
        """Ajoute une page à l'index."""
        tokens = _tokenize(content)
        self._tokens.append(tokens)
        self._metadata.append(
            {
                "page_id": page_id,
                "page_number": page_number,
                "document_name": document_name,
                "content": content or "",
            }
        )

    def build(self) -> None:
        """Finalise l'index après l'ajout de toutes les pages. Doit être
        appelé avant search()."""
        if not self._tokens:
            self._bm25 = None
            return
        self._bm25 = BM25Okapi(self._tokens)

    def search(self, query: str, top_k: int | None = None) -> list[SearchResult]:
        """Recherche les pages les plus pertinentes pour la requête.
        Renvoie au plus top_k résultats (défaut: settings.BM25_TOP_K).

        Note : BM25Okapi peut donner un score de 0 quand un terme apparaît
        dans la moitié des documents (IDF = log(1) = 0). On filtre donc sur
        la présence d'au moins un token de la requête dans le contenu, et
        on trie par score BM25 pour départager."""
        if self._bm25 is None:
            return []
        k = top_k or settings.BM25_TOP_K
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        scores = self._bm25.get_scores(query_tokens)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results: list[SearchResult] = []
        for idx, score in ranked[:k]:
            meta = self._metadata[idx]
            content_lower = (meta["content"] or "").lower()
            if not any(token in content_lower for token in query_tokens):
                continue
            results.append(
                SearchResult(
                    page_id=meta["page_id"],
                    page_number=meta["page_number"],
                    document_name=meta["document_name"],
                    score=float(score),
                    excerpt=_make_excerpt(meta["content"], query_tokens),
                )
            )
        return results


def _make_excerpt(content: str, query_tokens: list[str], window: int = 200) -> str:
    """Extrait un court extrait autour de la première occurrence d'un
    terme de la requête."""
    if not content:
        return ""
    lower_content = content.lower()
    for token in query_tokens:
        pos = lower_content.find(token)
        if pos != -1:
            start = max(0, pos - window // 2)
            end = min(len(content), pos + window // 2)
            prefix = "..." if start > 0 else ""
            suffix = "..." if end < len(content) else ""
            return f"{prefix}{content[start:end]}{suffix}"
    return content[:window]


def document_label(document: dict) -> str:
    """Nom du document, suivi de sa source s'il en a une (« passeport.pdf — source : Guichet »)."""
    name = document.get("name", "")
    source = (document.get("source") or {}).get("name")
    return f"{name} — source : {source}" if source else name


def build_index_from_dossier(dossier: dict) -> BM25Index:
    """Construit un index BM25 à partir des pages d'un dossier récupéré
    via l'API interne (get_dossier)."""
    index = BM25Index()
    for document in dossier.get("documents", []):
        doc_name = document_label(document)
        for page in document.get("pages", []):
            index.add_page(
                page_id=page["id"],
                page_number=page["page_number"],
                document_name=doc_name,
                content=page.get("content") or "",
            )
    index.build()
    logger.info(
        "BM25 index built for dossier %s: %d pages",
        dossier.get("id", "?"),
        len(index._metadata),
    )
    return index
