"""toutes les conversations s'ouvrent sur la présentation du dossier

Revision ID: 3b8d42bb1c0d
Revises: ff2cad14a4b0
Create Date: 2026-11-02 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b8d42bb1c0d"
down_revision: str | None = "ff2cad14a4b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # La présentation se calcule à la demande et ne dépend pas de l'historique : les conversations d'avant l'ont aussi,
    # le drapeau n'a plus de raison d'être.
    op.drop_column("conversations", "with_presentation")


def downgrade() -> None:
    op.add_column("conversations", sa.Column("with_presentation", sa.Boolean(), nullable=False, server_default="true"))
