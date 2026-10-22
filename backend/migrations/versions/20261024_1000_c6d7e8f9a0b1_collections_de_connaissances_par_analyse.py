"""collections de la base de connaissances par analyse

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-10-24 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c6d7e8f9a0b1"
down_revision: str | None = "b5c6d7e8f9a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Une valeur d'enum ne peut pas être ajoutée dans une transaction avec usage immédiat.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE versioned_field ADD VALUE IF NOT EXISTS 'KNOWLEDGE_COLLECTIONS'")

    op.add_column(
        "analyses",
        sa.Column(
            "knowledge_collections", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"
        ),
    )
    op.alter_column("analyses", "knowledge_collections", server_default=None)


def downgrade() -> None:
    op.drop_column("analyses", "knowledge_collections")
    # La valeur d'enum 'KNOWLEDGE_COLLECTIONS' reste : PostgreSQL ne sait pas retirer une valeur d'un enum, et les
    # versions déjà enregistrées pourraient la porter.
