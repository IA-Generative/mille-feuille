"""réglages de recherche par analyse, index de recherche et reconstructions par dossier

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-10-27 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f9a0b1c2d3e4"
down_revision: str | None = "e8f9a0b1c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Une valeur d'enum ne peut pas être ajoutée dans une transaction avec usage immédiat.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE versioned_field ADD VALUE IF NOT EXISTS 'SEARCH_SETTINGS'")

    op.add_column(
        "analyses",
        sa.Column("search_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    op.alter_column("analyses", "search_settings", server_default=None)

    search_index_status = postgresql.ENUM("INDEXING", "READY", "ERROR", name="search_index_status")
    op.create_table(
        "dossier_search_indexes",
        sa.Column("dossier_id", sa.UUID(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", search_index_status, nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dossier_id"], ["dossiers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("dossier_id"),
    )

    rebuild_status = postgresql.ENUM(
        "BUILDING", "SWAPPED", "FINALIZED", "ROLLED_BACK", "FAILED", name="index_rebuild_status"
    )
    op.create_table(
        "index_rebuilds",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("dossier_id", sa.UUID(), nullable=False),
        sa.Column("status", rebuild_status, nullable=False),
        sa.Column("target_fingerprint", sa.String(), nullable=False),
        sa.Column("target_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("previous_fingerprint", sa.String(), nullable=True),
        sa.Column("previous_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("total_pages", sa.Integer(), nullable=False),
        sa.Column("done_pages", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(), nullable=False),
        sa.Column("swapped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dossier_id"], ["dossiers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_index_rebuilds_dossier_id", "index_rebuilds", ["dossier_id"])
    op.create_index(
        "uq_index_rebuilds_active_per_dossier",
        "index_rebuilds",
        ["dossier_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('BUILDING', 'SWAPPED')"),
    )


def downgrade() -> None:
    op.drop_table("index_rebuilds")
    op.drop_table("dossier_search_indexes")
    op.execute("DROP TYPE IF EXISTS index_rebuild_status")
    op.execute("DROP TYPE IF EXISTS search_index_status")
    op.drop_column("analyses", "search_settings")
    # La valeur d'enum 'SEARCH_SETTINGS' reste : PostgreSQL ne sait pas retirer une valeur d'un enum, et les
    # versions déjà enregistrées pourraient la porter.
