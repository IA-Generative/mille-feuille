"""modèles LLM, capacités définies par l'administrateur et réglage du choix du modèle

Revision ID: 3a7d9e1c5b28
Revises: 5e9a3c7b1d42
Create Date: 2026-11-05 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3a7d9e1c5b28"
down_revision: str | None = "5e9a3c7b1d42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_capabilities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "llm_models",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("types", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_llm_models_position", "llm_models", ["position"])
    op.create_table(
        "llm_model_capabilities",
        sa.Column("model_id", sa.UUID(), nullable=False),
        sa.Column("capability_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["llm_models.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["capability_id"], ["llm_capabilities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("model_id", "capability_id"),
    )
    op.create_table(
        "llm_routing_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("auto_mode", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("llm_routing_settings")
    op.drop_table("llm_model_capabilities")
    op.drop_index("ix_llm_models_position", table_name="llm_models")
    op.drop_table("llm_models")
    op.drop_table("llm_capabilities")
