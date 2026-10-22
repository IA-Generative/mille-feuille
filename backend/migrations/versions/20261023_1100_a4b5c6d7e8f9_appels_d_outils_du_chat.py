"""appels d'outils du chat, avec leur décision

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-10-23 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"
down_revision: str | None = "f3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_tool_calls",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("llm_call_id", sa.String(), nullable=False),
        sa.Column("function_name", sa.String(), nullable=False),
        sa.Column("tool_id", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("server_name", sa.String(), nullable=False),
        sa.Column("arguments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("side_effect", sa.Boolean(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "APPROVED", "REFUSED", "EXECUTED", "SUPERSEDED", name="chat_tool_call_status"),
            nullable=False,
        ),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_tool_calls_conversation_id"), "chat_tool_calls", ["conversation_id"], unique=False)
    op.create_index(op.f("ix_chat_tool_calls_message_id"), "chat_tool_calls", ["message_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_tool_calls_message_id"), table_name="chat_tool_calls")
    op.drop_index(op.f("ix_chat_tool_calls_conversation_id"), table_name="chat_tool_calls")
    op.drop_table("chat_tool_calls")
    sa.Enum(name="chat_tool_call_status").drop(op.get_bind(), checkfirst=True)
