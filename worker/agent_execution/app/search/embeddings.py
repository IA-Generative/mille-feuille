"""Vecteurs d'un passage : dense (embedding du modèle choisi dans l'analyse) et creux (lexical, BM25).

Le vecteur dense vient d'un modèle servi par le hub compatible OpenAI (`/embeddings`). Le vecteur creux est calculé
ici : tokenisation, minuscules, retrait des accents, mots vides et racinisation française. Chaque terme devient un
indice stable (empreinte sur 32 bits) ; le poids est la partie « fréquence » de BM25 (saturation et normalisation par
la longueur). L'IDF, lui, est calculé par Qdrant à partir des statistiques de la collection.

Le même calcul sert à l'indexation et à la requête."""

import hashlib
import re
import unicodedata
from collections import Counter

from py_rust_stemmers import SnowballStemmer

from app.config import settings
from app.llm import _client

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_STEMMER = SnowballStemmer("french")

# Mots vides du français : sans accents, comme les termes qu'ils filtrent.
_STOP_WORDS = frozenset(
    "a au aux avec ce ces cet cette dans de des du elle en et il ils je la le les leur lui ma mais me meme mes moi "
    "mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi ton tu un une vos votre "
    "vous c d j l m n s t y est sont etre ete avoir ont a ai as avons avez comme si plus tout tous".split()
)


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def tokenize(text: str) -> list[str]:
    """Les termes d'un texte : sans accents, en minuscules, sans mots vides, ramenés à leur racine."""
    words = [_strip_accents(word.lower()) for word in _WORD_RE.findall(text or "")]
    return _STEMMER.stem_words([word for word in words if word not in _STOP_WORDS])


def term_index(term: str) -> int:
    """Indice stable d'un terme (32 bits) : le même sur tous les workers et d'une exécution à l'autre."""
    return int.from_bytes(hashlib.blake2b(term.encode(), digest_size=4).digest(), "big")


def encode_sparse(text: str) -> dict:
    """Vecteur creux d'un passage à indexer : poids BM25 (sans IDF) de chacun de ses termes."""
    tokens = tokenize(text)
    if not tokens:
        return {"indices": [], "values": []}
    k1, b = settings.SPARSE_BM25_K1, settings.SPARSE_BM25_B
    length_norm = 1 - b + b * len(tokens) / settings.SPARSE_AVG_LENGTH
    weights: dict[int, float] = {}
    for term, frequency in Counter(tokens).items():
        # Deux termes qui tombent sur le même indice (collision, très rare) se cumulent.
        index = term_index(term)
        weights[index] = weights.get(index, 0.0) + frequency * (k1 + 1) / (frequency + k1 * length_norm)
    return {"indices": list(weights), "values": list(weights.values())}


def encode_sparse_query(text: str) -> dict:
    """Vecteur creux d'une requête : chaque terme distinct compte une fois, l'IDF fait le reste côté serveur."""
    indices = list(dict.fromkeys(term_index(term) for term in tokenize(text)))
    return {"indices": indices, "values": [1.0] * len(indices)}


def embed_dense(texts: list[str], model: str) -> list[list[float]]:
    """Embeddings des textes avec le modèle donné, par lots, dans l'ordre. Le hub peut renvoyer les lots dans le
    désordre : on retrie sur l'index de chaque réponse."""
    vectors: list[list[float]] = []
    client = _client()
    size = max(1, settings.EMBEDDING_BATCH_SIZE)
    for start in range(0, len(texts), size):
        batch = texts[start : start + size]
        response = client.embeddings.create(model=model, input=batch)
        ordered = sorted(response.data, key=lambda item: item.index)
        if len(ordered) != len(batch):
            raise RuntimeError(f"Le modèle d'embeddings a renvoyé {len(ordered)} vecteurs pour {len(batch)} textes.")
        vectors.extend(list(item.embedding) for item in ordered)
    return vectors
