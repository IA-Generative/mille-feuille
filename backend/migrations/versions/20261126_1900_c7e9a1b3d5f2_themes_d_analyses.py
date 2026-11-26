"""thèmes d'analyses : tables, thème de l'analyse et son historique

Revision ID: c7e9a1b3d5f2
Revises: b4d6f8a0c2e1
Create Date: 2026-11-26 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c7e9a1b3d5f2"
down_revision: str | None = "b4d6f8a0c2e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE versioned_field ADD VALUE IF NOT EXISTS 'THEME'")
    op.create_table(
        "analyse_themes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(), nullable=True),
        _timestamp(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ux_analyse_themes_lower_name", "analyse_themes", [sa.text("lower(name)")], unique=True)
    op.create_table(
        "analyse_theme_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("theme_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        _timestamp(),
        sa.ForeignKeyConstraint(["theme_id"], ["analyse_themes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analyse_theme_versions_theme_id", "analyse_theme_versions", ["theme_id"])
    op.add_column("analyses", sa.Column("theme_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_analyses_theme_id", "analyses", "analyse_themes", ["theme_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_analyses_theme_id", "analyses", ["theme_id"])


def downgrade() -> None:
    # La valeur 'THEME' reste dans le type : PostgreSQL ne sait pas la retirer.
    op.execute("DELETE FROM field_versions WHERE field = 'THEME'")
    op.drop_index("ix_analyses_theme_id", table_name="analyses")
    op.drop_constraint("fk_analyses_theme_id", "analyses", type_="foreignkey")
    op.drop_column("analyses", "theme_id")
    op.drop_table("analyse_theme_versions")
    op.drop_table("analyse_themes")
