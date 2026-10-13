"""verdicts des appelants et condensé non sensible des runs éphémères (métriques)

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-18 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ephemeral_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prediction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "kind", postgresql.ENUM("LABEL", "ENTITY", name="prediction_kind", create_type=False), nullable=False
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "source",
            postgresql.ENUM("TEXTUAL", "VISUAL", "GLINER", name="prediction_source", create_type=False),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.Enum("CORRECT", "INCORRECT", name="ephemeral_verdict"), nullable=False),
        sa.Column("expected_name", sa.String(), nullable=True),
        sa.UniqueConstraint("run_id", "prediction_id", "created_by", name="uq_ephemeral_feedback_verdict"),
    )
    op.create_table(
        "ephemeral_run_metrics",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.Column("predictions", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_ephemeral_run_metrics_created_by", "ephemeral_run_metrics", ["created_by"])
    op.create_index("ix_ephemeral_feedback_run_id", "ephemeral_feedback", ["run_id"])
    op.create_index("ix_ephemeral_feedback_created_by", "ephemeral_feedback", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_ephemeral_feedback_created_by", table_name="ephemeral_feedback")
    op.drop_index("ix_ephemeral_feedback_run_id", table_name="ephemeral_feedback")
    op.drop_table("ephemeral_feedback")
    op.drop_index("ix_ephemeral_run_metrics_created_by", table_name="ephemeral_run_metrics")
    op.drop_table("ephemeral_run_metrics")
    sa.Enum(name="ephemeral_verdict").drop(op.get_bind(), checkfirst=True)
