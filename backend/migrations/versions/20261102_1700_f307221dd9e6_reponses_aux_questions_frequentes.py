"""réponses prêtes aux questions fréquentes d'un dossier

Revision ID: f307221dd9e6
Revises: 460b817af7ba
Create Date: 2026-11-02 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f307221dd9e6"
down_revision: str | None = "460b817af7ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status = postgresql.ENUM("EN_COURS", "REPONDUE", "SANS_REPONSE", "ECHEC", name="question_answer_status")
    op.create_table(
        "dossier_question_answers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("dossier_id", sa.UUID(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dossier_id"], ["dossiers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dossier_id", "question", name="uq_dossier_question_answer"),
    )
    op.create_index("ix_dossier_question_answers_dossier_id", "dossier_question_answers", ["dossier_id"])


def downgrade() -> None:
    op.drop_table("dossier_question_answers")
    op.execute("DROP TYPE IF EXISTS question_answer_status")
