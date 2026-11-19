"""ordre explicite des labels et des entités, exemples de label, labels et zones où chercher une entité

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
    op.add_column(
        "entity_definitions",
        sa.Column("zones", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.create_table(
        "entity_definition_labels",
        sa.Column("entity_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_definition_id"], ["entity_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["label_definition_id"], ["label_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("entity_definition_id", "label_definition_id"),
    )
    op.create_table(
        "label_examples",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("s3_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["label_id"], ["label_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_label_examples_label_id", "label_examples", ["label_id"])


def downgrade() -> None:
    op.drop_index("ix_label_examples_label_id", table_name="label_examples")
    op.drop_table("label_examples")
    op.drop_table("entity_definition_labels")
    op.drop_column("entity_definitions", "zones")
    op.drop_column("entity_definitions", "position")
    op.drop_column("label_definitions", "position")
