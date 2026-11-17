"""nature des définitions d'entités : entité nommée (GLiNER) ou sémantique (LLM)

Revision ID: 7b2c4e6a8d10
Revises: 3a7d9e1c5b28
Create Date: 2026-11-06 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b2c4e6a8d10"
down_revision: str | None = "3a7d9e1c5b28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    nature = sa.Enum("ENTITE", "SEMANTIQUE", name="entity_nature")
    nature.create(op.get_bind(), checkfirst=True)
    op.add_column("entity_definitions", sa.Column("nature", nature, nullable=False, server_default="ENTITE"))
    # GLiNER n'extrait pas les booléens : ils restaient au LLM, ils deviennent sémantiques.
    op.execute("UPDATE entity_definitions SET nature = 'SEMANTIQUE' WHERE type = 'BOOLEEN'")


def downgrade() -> None:
    op.drop_column("entity_definitions", "nature")
    sa.Enum(name="entity_nature").drop(op.get_bind(), checkfirst=True)
