"""source de prédiction « gliner » (extraction d'entités avec GLiNER2.5)

Revision ID: c4d5e6f7a8b9
Revises: a2b3c4d5e6f7
Create Date: 2026-10-17 09:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Une valeur d'enum ne peut pas être ajoutée dans une transaction avec usage immédiat.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE prediction_source ADD VALUE IF NOT EXISTS 'GLINER'")


def downgrade() -> None:
    # PostgreSQL ne sait pas retirer une valeur d'un enum : on ne touche pas au type, on convertit les données.
    op.execute("UPDATE document_predictions SET source = 'TEXTUAL' WHERE source = 'GLINER'")
