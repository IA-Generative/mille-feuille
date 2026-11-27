"""chiffrer en base les noms et les e-mails des personnes

Demande ENCRYPTION_KEYS et EMAIL_INDEX_KEY dès que des données existent.

Revision ID: e2a4c6b8d0f1
Revises: d1f3a5c7e9b2
Create Date: 2026-11-27 17:00:00
"""

import sqlalchemy as sa
from alembic import op

from app.core.data_encryption import decrypt_existing, encrypt_existing

revision = "e2a4c6b8d0f1"
down_revision = "d1f3a5c7e9b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_users", sa.Column("email_index", sa.String(), nullable=True))
    op.create_index("ix_app_users_email_index", "app_users", ["email_index"])
    encrypt_existing(op.get_bind())


def downgrade() -> None:
    decrypt_existing(op.get_bind())
    op.drop_index("ix_app_users_email_index", table_name="app_users")
    op.drop_column("app_users", "email_index")
