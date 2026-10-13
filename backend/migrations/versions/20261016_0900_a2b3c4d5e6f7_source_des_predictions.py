"""source des prédictions : textuelle ou visuelle (CLIP)

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-10-16 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    source = sa.Enum("TEXTUAL", "VISUAL", name="prediction_source")
    source.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "document_predictions",
        sa.Column("source", source, nullable=False, server_default="TEXTUAL"),
    )


def downgrade() -> None:
    op.drop_column("document_predictions", "source")
    sa.Enum(name="prediction_source").drop(op.get_bind(), checkfirst=True)
