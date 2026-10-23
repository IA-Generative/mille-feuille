"""numéro cité des sources d'un message

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-10-26 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8f9a0b1c2d3"
down_revision: str | None = "d7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("message_sources", sa.Column("number", sa.Integer(), nullable=True))
    op.add_column("message_external_sources", sa.Column("number", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("message_external_sources", "number")
    op.drop_column("message_sources", "number")
