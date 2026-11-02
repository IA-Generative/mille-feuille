"""détail de l'exécution d'une réponse de l'assistant

Revision ID: 5e9a3c7b1d42
Revises: 8c1f4a7d2e95
Create Date: 2026-11-02 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5e9a3c7b1d42"
down_revision: str | None = "8c1f4a7d2e95"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL pour les messages existants : leur exécution n'a pas été gardée.
    op.add_column("messages", sa.Column("execution", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "execution")
