"""reprendre les groupes Keycloak dans les groupes de l'application

Demande ENCRYPTION_KEYS et EMAIL_INDEX_KEY dès que des groupes sont à reprendre.

Revision ID: a4c6e8f0b2d3
Revises: f3b5d7e9a1c2
Create Date: 2026-11-27 21:00:00
"""

import sqlalchemy as sa
from alembic import op

from app.services.legacy_groups import convert_keycloak_groups, restore_keycloak_groups

revision = "a4c6e8f0b2d3"
down_revision = "f3b5d7e9a1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_groups", sa.Column("keycloak_path", sa.String(), nullable=True))
    op.alter_column("dossier_group_access", "keycloak_group", new_column_name="group_id")
    convert_keycloak_groups(op.get_bind())


def downgrade() -> None:
    restore_keycloak_groups(op.get_bind())
    op.alter_column("dossier_group_access", "group_id", new_column_name="keycloak_group")
    op.drop_column("app_groups", "keycloak_path")
