"""thèmes de ressemblance, leurs versions, les groupes trouvés et les rapprochements écartés

Revision ID: e8a0c2d4f6b8
Revises: d7f9b1c3e5a7
Create Date: 2026-11-28 16:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e8a0c2d4f6b8"
down_revision: str | None = "d7f9b1c3e5a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)


def _created() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def _theme(**kwargs) -> sa.Column:
    return sa.Column(
        "theme_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("resemblance_themes.id", ondelete="CASCADE"),
        nullable=False,
        **kwargs,
    )


def upgrade() -> None:
    op.create_table(
        "resemblance_themes",
        _id(),
        _created(),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("certainty", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("criteria", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "resemblance_theme_versions",
        _id(),
        _created(),
        _theme(index=True),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
    )
    op.create_table(
        "resemblance_members",
        _theme(primary_key=True),
        sa.Column("group_key", sa.String(64), primary_key=True),
        sa.Column(
            "dossier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dossiers.id", ondelete="CASCADE"),
            primary_key=True,
            index=True,
        ),
    )
    op.create_table(
        "resemblance_dismissals",
        _id(),
        _created(),
        _theme(index=True),
        sa.Column("group_key", sa.String(64), nullable=False),
        sa.Column("dismissed_by", sa.String(), nullable=False),
        sa.Column("dismissed_by_name", sa.String(), nullable=True),
        sa.Column("restored_by", sa.String(), nullable=True),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    for table in ("resemblance_dismissals", "resemblance_members", "resemblance_theme_versions", "resemblance_themes"):
        op.drop_table(table)
