"""registre des tools et serveurs MCP

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-10-22 20:05:02.679615

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c0d1e2f3a4b5"
down_revision: str | None = "b9c0d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tool_servers",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column(
            "auth_mode", sa.Enum("NONE", "TOKEN_EXCHANGE", "STATIC_TOKEN", name="tool_auth_mode"), nullable=False
        ),
        sa.Column("visibility", sa.Enum("PRIVATE", "GROUPS", "ALL", name="tool_visibility"), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("owner_name", sa.String(), nullable=False),
        sa.Column("groups", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("credentials", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tool_servers_created_by"), "tool_servers", ["created_by"], unique=False)
    op.create_table(
        "tools",
        sa.Column("server_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("input_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("side_effect", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["server_id"], ["tool_servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_id", "name", name="uq_tools_server_id_name"),
    )
    op.create_index(op.f("ix_tools_server_id"), "tools", ["server_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tools_server_id"), table_name="tools")
    op.drop_table("tools")
    op.drop_index(op.f("ix_tool_servers_created_by"), table_name="tool_servers")
    op.drop_table("tool_servers")
    sa.Enum(name="tool_visibility").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tool_auth_mode").drop(op.get_bind(), checkfirst=True)
