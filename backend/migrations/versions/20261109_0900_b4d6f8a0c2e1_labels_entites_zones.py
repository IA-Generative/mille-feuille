"""ordre explicite des labels et des entités, label et zones où chercher une entité

Revision ID: b4d6f8a0c2e1
Revises: 9d3e5f7a1b24
Create Date: 2026-11-09 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b4d6f8a0c2e1"
down_revision: str | None = "9d3e5f7a1b24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("label_definitions", "entity_definitions"):
        op.add_column(table, sa.Column("position", sa.Integer(), nullable=False, server_default="0"))
        # Le rang reprend l'ordre actuel (création), analyse par analyse.
        op.execute(
            f"UPDATE {table} t SET position = r.rank FROM ("
            f"SELECT id, ROW_NUMBER() OVER (PARTITION BY analyse_id ORDER BY created_at, id) - 1 AS rank FROM {table}"
            ") r WHERE t.id = r.id"
        )
    op.add_column("entity_definitions", sa.Column("label_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "entity_definitions",
        sa.Column("zones", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.create_foreign_key(
        "fk_entity_definitions_label_id",
        "entity_definitions",
        "label_definitions",
        ["label_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_entity_definitions_label_id", "entity_definitions", type_="foreignkey")
    op.drop_column("entity_definitions", "zones")
    op.drop_column("entity_definitions", "label_id")
    op.drop_column("entity_definitions", "position")
    op.drop_column("label_definitions", "position")
