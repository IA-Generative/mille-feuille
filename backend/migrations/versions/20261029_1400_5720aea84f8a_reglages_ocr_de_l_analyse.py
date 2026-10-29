"""réglages de lecture des documents scannés par analyse (modèle qui décrit les images)

Revision ID: 5720aea84f8a
Revises: f9a0b1c2d3e4
Create Date: 2026-10-29 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5720aea84f8a"
down_revision: str | None = "f9a0b1c2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Une valeur d'enum ne peut pas être ajoutée dans une transaction avec usage immédiat.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE versioned_field ADD VALUE IF NOT EXISTS 'OCR_SETTINGS'")

    op.add_column(
        "analyses",
        sa.Column("ocr_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    op.alter_column("analyses", "ocr_settings", server_default=None)


def downgrade() -> None:
    op.drop_column("analyses", "ocr_settings")
    # La valeur d'enum 'OCR_SETTINGS' reste : PostgreSQL ne sait pas retirer une valeur d'un enum, et les versions
    # déjà enregistrées pourraient la porter.
