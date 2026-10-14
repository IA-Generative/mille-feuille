"""sources des fichiers : catalogue d'analyse ou source tampon d'un dossier, rattachées aux documents

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-10-19 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("analyse_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analyses.id", ondelete="CASCADE")),
        sa.Column("dossier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dossiers.id", ondelete="CASCADE")),
        sa.CheckConstraint("(analyse_id IS NULL) <> (dossier_id IS NULL)", name="ck_document_source_one_owner"),
    )
    op.create_index("ix_document_sources_analyse_id", "document_sources", ["analyse_id"])
    op.create_index("ix_document_sources_dossier_id", "document_sources", ["dossier_id"])
    op.create_index(
        "uq_document_source_analyse_name",
        "document_sources",
        ["analyse_id", "name"],
        unique=True,
        postgresql_where=sa.text("analyse_id IS NOT NULL"),
    )
    op.create_index(
        "uq_document_source_dossier_name",
        "document_sources",
        ["dossier_id", "name"],
        unique=True,
        postgresql_where=sa.text("dossier_id IS NOT NULL"),
    )

    op.add_column(
        "dossier_documents",
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_dossier_documents_source_id", "dossier_documents", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_dossier_documents_source_id", table_name="dossier_documents")
    op.drop_column("dossier_documents", "source_id")
    op.drop_table("document_sources")
