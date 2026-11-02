"""conversation ouverte sur la présentation du dossier

Revision ID: ff2cad14a4b0
Revises: f307221dd9e6
Create Date: 2026-11-02 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ff2cad14a4b0"
down_revision: str | None = "f307221dd9e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Les conversations existantes gardent leur page : seules les nouvelles s'ouvrent sur la présentation.
    op.add_column("conversations", sa.Column("with_presentation", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("conversations", "with_presentation")
