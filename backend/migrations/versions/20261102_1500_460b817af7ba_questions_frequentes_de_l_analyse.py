"""questions fréquentes de l'analyse (versionnées)

Revision ID: 460b817af7ba
Revises: 5720aea84f8a
Create Date: 2026-11-02 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "460b817af7ba"
down_revision: str | None = "5720aea84f8a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Une valeur d'enum ne peut pas être ajoutée dans une transaction avec usage immédiat.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE versioned_field ADD VALUE IF NOT EXISTS 'FREQUENT_QUESTIONS'")

    op.add_column(
        "analyses",
        sa.Column("frequent_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.alter_column("analyses", "frequent_questions", server_default=None)


def downgrade() -> None:
    op.drop_column("analyses", "frequent_questions")
    # La valeur d'enum 'FREQUENT_QUESTIONS' reste : PostgreSQL ne sait pas retirer une valeur d'un enum, et les versions
    # déjà enregistrées pourraient la porter.
