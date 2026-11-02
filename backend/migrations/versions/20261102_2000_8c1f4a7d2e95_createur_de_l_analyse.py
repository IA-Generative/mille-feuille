"""créateur de l'analyse, historique du nom et de la description

Revision ID: 8c1f4a7d2e95
Revises: 3b8d42bb1c0d
Create Date: 2026-11-02 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8c1f4a7d2e95"
down_revision: str | None = "3b8d42bb1c0d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Une valeur d'enum ne peut pas être ajoutée dans une transaction avec usage immédiat.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE versioned_field ADD VALUE IF NOT EXISTS 'NAME'")
        op.execute("ALTER TYPE versioned_field ADD VALUE IF NOT EXISTS 'DESCRIPTION'")

    # NULL pour les analyses existantes : leur créateur n'est pas connu, seuls les administrateurs les gèrent.
    op.add_column("analyses", sa.Column("created_by", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("analyses", "created_by")
    # Les valeurs d'enum 'NAME' et 'DESCRIPTION' restent : PostgreSQL ne sait pas retirer une valeur d'un enum, et les
    # versions déjà enregistrées pourraient la porter.
