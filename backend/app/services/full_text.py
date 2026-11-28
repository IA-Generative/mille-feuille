"""Briques de la recherche plein texte PostgreSQL, partagées par la recherche dans les conversations (#650) et à
travers les dossiers (#642) : français, insensible aux accents, tolérante aux débuts de mots.

Les configurations `french_unaccent` et `simple_unaccent` viennent de la migration `d1f3a5c7e9b2`.
"""

import functools
import re
from typing import Any

from sqlalchemy import ColumnElement, func, literal_column

MAX_TERMS = 10

# Littéraux, jamais des paramètres liés : les expressions doivent être identiques à celles des index.
FRENCH = literal_column("'french_unaccent'::regconfig")
_SIMPLE = literal_column("'simple_unaccent'::regconfig")
# Un tsvector est limité à 1 Mo : au-delà, la fin d'un très long texte n'est pas cherchée.
INDEXED_LENGTH = literal_column("100000")

# Bornes des mots surlignés par `ts_headline` : des caractères de contrôle, retirés du texte avant surlignage.
_START, _STOP = "\x02", "\x03"
HEADLINE_OPTIONS = f'StartSel="{_START}", StopSel="{_STOP}", MaxWords=18, MinWords=8, MaxFragments=1'


def search_terms(query: str) -> list[str]:
    """Les mots cherchés. Ne gardent que lettres et chiffres : aucun opérateur de `to_tsquery` ne passe."""
    return re.findall(r"[^\W_]+", query)[:MAX_TERMS]


def vector(text: ColumnElement[str]) -> ColumnElement[Any]:
    cut = func.left(text, INDEXED_LENGTH)
    return func.tsvector_concat(func.to_tsvector(FRENCH, cut), func.to_tsvector(_SIMPLE, cut))


def term_query(term: str) -> ColumnElement[Any]:
    """Un mot sous une forme proche (pluriel, accord) **ou** comme début de mot."""
    return func.tsquery_or(func.to_tsquery(FRENCH, term), func.to_tsquery(_SIMPLE, f"{term}:*"))


def all_terms(terms: list[str]) -> ColumnElement[Any]:
    return functools.reduce(func.tsquery_and, [term_query(term) for term in terms])


def any_term(terms: list[str]) -> ColumnElement[Any]:
    return functools.reduce(func.tsquery_or, [term_query(term) for term in terms])


def plain_text(text: ColumnElement[str]) -> ColumnElement[str]:
    """Le texte d'un extrait : sans les marques de mise en forme, illisibles, ni les bornes de surlignage."""
    return func.regexp_replace(func.left(text, INDEXED_LENGTH), f"[*`#|{_START}{_STOP}]+", "", "g")


def headline(text: ColumnElement[str], tsquery: ColumnElement[Any]) -> ColumnElement[str]:
    """Extrait surligné. Coûteux : à ne calculer que pour les lignes affichées."""
    return func.ts_headline(FRENCH, plain_text(text), tsquery, HEADLINE_OPTIONS)


def split_headline(value: str) -> list[tuple[str, bool]]:
    """Découpe un extrait en morceaux `(texte, surligné)`."""
    parts = re.split(f"[{_START}{_STOP}]", " ".join(value.split()))
    # Les bornes alternent : les morceaux de rang impair sont entre un début et une fin.
    return [(part, index % 2 == 1) for index, part in enumerate(parts) if part]
