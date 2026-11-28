"""recherche à travers les dossiers : vecteur de recherche des pages et index plein texte

Revision ID: c6e8a0b2d4f6
Revises: b5d7f9a1c3e5
Create Date: 2026-11-28 10:00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c6e8a0b2d4f6"
down_revision: str | None = "b5d7f9a1c3e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _vector(text: str) -> str:
    return (
        f"tsvector_concat(to_tsvector('french_unaccent'::regconfig, left({text}, 100000)), "
        f"to_tsvector('simple_unaccent'::regconfig, left({text}, 100000)))"
    )


# Les expressions doivent rester identiques à celles de `dossier_search_repository`, sinon les index ne servent pas.
INDEXES = (
    ("ix_dossiers_search", "dossiers", _vector("translate(name, '_.-/', '    ')")),
    ("ix_dossier_documents_search", "dossier_documents", _vector("translate(name, '_.-/', '    ')")),
    (
        "ix_analysis_element_versions_search",
        "analysis_element_versions",
        _vector("coalesce(value ->> 'value', value ->> 'label')"),
    ),
)


def upgrade() -> None:
    # La clé qui rapproche deux valeurs (casse, accents, espaces). Une fonction pour pouvoir l'indexer : `unaccent`
    # seule n'est pas immuable. Le corps « RETURN » fixe le dictionnaire à la création (PostgreSQL 14 ou plus).
    op.execute(
        "CREATE FUNCTION dossier_link_key(value text) RETURNS text LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE "
        "RETURN lower(unaccent('unaccent'::regdictionary, btrim(regexp_replace(value, '\\s+', ' ', 'g'))))"
    )
    # `left` : une très longue valeur dépasserait la taille admise par un index.
    op.execute(
        "CREATE INDEX ix_analysis_element_versions_link ON analysis_element_versions "
        "(dossier_link_key(left(coalesce(value ->> 'value', value ->> 'label'), 300)))"
    )
    # Le vecteur d'une page est enregistré : le recalculer à chaque recherche coûterait trop sur de longs textes.
    # Cette colonne réécrit la table : la migration est plus longue sur une base déjà remplie.
    vector = _vector("content")
    op.execute(f"ALTER TABLE document_pages ADD COLUMN search_vector tsvector GENERATED ALWAYS AS ({vector}) STORED")
    op.execute("CREATE INDEX ix_document_pages_search ON document_pages USING gin (search_vector)")
    for name, table, expression in INDEXES:
        op.execute(f"CREATE INDEX {name} ON {table} USING gin ({expression})")


def downgrade() -> None:
    for name, _, _ in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
    op.execute("ALTER TABLE document_pages DROP COLUMN search_vector")
    op.execute("DROP INDEX IF EXISTS ix_analysis_element_versions_link")
    op.execute("DROP FUNCTION IF EXISTS dossier_link_key(text)")
