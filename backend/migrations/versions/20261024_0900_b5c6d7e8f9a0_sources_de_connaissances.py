"""sources de connaissances

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-10-24 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b5c6d7e8f9a0"
down_revision: str | None = "a4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_sources",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column(
            "auth_mode",
            postgresql.ENUM("NONE", "TOKEN_EXCHANGE", "STATIC_TOKEN", name="tool_auth_mode", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "visibility",
            postgresql.ENUM("PRIVATE", "GROUPS", "ALL", name="tool_visibility", create_type=False),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("owner_name", sa.String(), nullable=False),
        sa.Column("groups", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("audience", sa.String(), nullable=True),
        sa.Column("credentials", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_sources_created_by"), "knowledge_sources", ["created_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_sources_created_by"), table_name="knowledge_sources")
    op.drop_table("knowledge_sources")
