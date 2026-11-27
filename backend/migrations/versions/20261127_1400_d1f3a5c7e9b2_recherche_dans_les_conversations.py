"""recherche dans les conversations : configurations de recherche plein texte et index des messages

Revision ID: d1f3a5c7e9b2
Revises: c7e9a1b3d5f2
Create Date: 2026-11-27 14:00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "d1f3a5c7e9b2"
down_revision: str | None = "c7e9a1b3d5f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Recherche insensible aux accents : `french_unaccent` rapproche les formes d'un mot (pluriel, accord),
# `simple_unaccent` garde le mot tel quel, pour trouver sur un début de mot pendant la frappe.
CONFIGURATIONS = (("french_unaccent", "french", "french_stem"), ("simple_unaccent", "simple", "simple"))


def upgrade() -> None:
    # Extension « trusted » depuis PostgreSQL 13 : le propriétaire de la base peut la créer.
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    for name, base, dictionary in CONFIGURATIONS:
        op.execute(f"CREATE TEXT SEARCH CONFIGURATION {name} (COPY = {base})")
        op.execute(
            f"ALTER TEXT SEARCH CONFIGURATION {name} "
            f"ALTER MAPPING FOR hword, hword_part, word WITH unaccent, {dictionary}"
        )
        op.execute(
            f"ALTER TEXT SEARCH CONFIGURATION {name} "
            f"ALTER MAPPING FOR asciihword, hword_asciipart, asciiword WITH {dictionary}"
        )
    # L'expression doit rester identique à celle de `conversation_search_repository`, sinon l'index ne sert pas.
    # `left` : un tsvector est limité à 1 Mo, un message très long ne doit pas faire échouer son enregistrement.
    op.execute(
        "CREATE INDEX ix_messages_search ON messages USING gin (tsvector_concat("
        "to_tsvector('french_unaccent'::regconfig, left(content, 100000)), "
        "to_tsvector('simple_unaccent'::regconfig, left(content, 100000))))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_messages_search")
    for name, _, _ in CONFIGURATIONS:
        op.execute(f"DROP TEXT SEARCH CONFIGURATION IF EXISTS {name}")
    # L'extension `unaccent` reste : elle peut servir à d'autres objets.
