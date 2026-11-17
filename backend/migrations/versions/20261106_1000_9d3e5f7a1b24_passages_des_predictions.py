"""passages des prédictions : texte brut et span de ce sur quoi repose une prédiction

Revision ID: 9d3e5f7a1b24
Revises: 7b2c4e6a8d10
Create Date: 2026-11-06 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d3e5f7a1b24"
down_revision: str | None = "7b2c4e6a8d10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prediction_passages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("prediction_id", sa.UUID(), nullable=False),
        sa.Column("document_page_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["prediction_id"], ["document_predictions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_page_id"], ["document_pages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prediction_passages_prediction_id", "prediction_passages", ["prediction_id"])
    op.create_index("ix_prediction_passages_document_page_id", "prediction_passages", ["document_page_id"])


def downgrade() -> None:
    op.drop_table("prediction_passages")
