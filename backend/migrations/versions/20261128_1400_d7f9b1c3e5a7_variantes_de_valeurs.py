"""rapprochements souples : clé des variantes d'une valeur et son index

Revision ID: d7f9b1c3e5a7
Revises: c6e8a0b2d4f6
Create Date: 2026-11-28 14:00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "d7f9b1c3e5a7"
down_revision: str | None = "c6e8a0b2d4f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Abréviations d'adresses. « r » ne vaut « rue » qu'après un numéro : ailleurs, c'est souvent une initiale.
ABBREVIATIONS = (
    (r"\m(av|ave)\M", "avenue"),
    (r"\m(bd|bld|boul)\M", "boulevard"),
    (r"\mpl\M", "place"),
    (r"\mche?m?\M", "chemin"),
    (r"(\m[0-9]+( bis| ter)?) r\M", r"\1 rue"),
)


def upgrade() -> None:
    # Reçoit la clé exacte (`dossier_link_key` : minuscules, sans accents). La ponctuation devient une espace, les
    # abréviations sont développées ; puis, avec un chiffre, on colle tout et on confond o/0 et i/l/1 (lecture de
    # scans, plaques, numéros) ; sans chiffre, on trie les mots (« durand emile » et « emile durand »).
    words = r"btrim(regexp_replace(key, '[^[:alnum:]]+', ' ', 'g'))"
    for pattern, replacement in ABBREVIATIONS:
        words = f"regexp_replace({words}, '{pattern}', '{replacement}', 'g')"
    op.execute(
        "CREATE FUNCTION dossier_link_loose_key(key text) RETURNS text LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE "
        "RETURN (SELECT CASE WHEN w.text ~ '[0-9]' THEN translate(replace(w.text, ' ', ''), 'oil', '011') "
        "ELSE array_to_string(ARRAY(SELECT part FROM unnest(string_to_array(w.text, ' ')) AS part ORDER BY part), ' ') "
        f"END FROM (SELECT {words} AS text) AS w)"
    )
    op.execute(
        "CREATE INDEX ix_analysis_element_versions_loose ON analysis_element_versions "
        "(dossier_link_loose_key(dossier_link_key(left(coalesce(value ->> 'value', value ->> 'label'), 300))))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_analysis_element_versions_loose")
    op.execute("DROP FUNCTION IF EXISTS dossier_link_loose_key(text)")
