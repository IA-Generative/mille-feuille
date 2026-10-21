"""consommation de tokens des appels au LLM

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-10-22 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9c0d1e2f3a4"
down_revision: str | None = "a8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "token_usages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("step", sa.String(), nullable=False),
        sa.Column("kind", sa.Enum("CHAT", "EMBEDDING", name="token_usage_kind"), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("dossier_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_token_usages_user_id"), "token_usages", ["user_id"], unique=False)
    op.create_index(op.f("ix_token_usages_created_at"), "token_usages", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_token_usages_created_at"), table_name="token_usages")
    op.drop_index(op.f("ix_token_usages_user_id"), table_name="token_usages")
    op.drop_table("token_usages")
    sa.Enum(name="token_usage_kind").drop(op.get_bind(), checkfirst=True)
