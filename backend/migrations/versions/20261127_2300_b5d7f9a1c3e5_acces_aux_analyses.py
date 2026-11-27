"""accès aux analyses : groupes, personnes ajoutées et historique

Les partages d'analyse par groupe déjà enregistrés deviennent les premiers accès. Une analyse sans groupe n'est plus
vue que des super admins.

Revision ID: b5d7f9a1c3e5
Revises: a4c6e8f0b2d3
Create Date: 2026-11-27 23:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b5d7f9a1c3e5"
down_revision = "a4c6e8f0b2d3"
branch_labels = None
depends_on = None


def _timestamp() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def _analyse(primary_key: bool = False) -> sa.Column:
    return sa.Column(
        "analyse_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("analyses.id", ondelete="CASCADE"),
        primary_key=primary_key,
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "analyse_groups",
        _analyse(primary_key=True),
        sa.Column("group_id", sa.String(), primary_key=True),
        sa.Column("granted_by", sa.String(), nullable=True),
        _timestamp(),
    )
    op.create_index("ix_analyse_groups_group_id", "analyse_groups", ["group_id"])
    op.create_table(
        "analyse_people",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _analyse(),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_roles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("email_index", sa.String(), nullable=True),
        sa.Column("added_by", sa.String(), nullable=True),
        _timestamp(),
        sa.UniqueConstraint("analyse_id", "user_id", name="ux_analyse_people_user"),
        sa.UniqueConstraint("analyse_id", "email_index", name="ux_analyse_people_email"),
        sa.CheckConstraint("user_id IS NOT NULL OR email_index IS NOT NULL", name="ck_analyse_people_identity"),
    )
    for column in ("analyse_id", "role_id", "user_id", "email_index"):
        op.create_index(f"ix_analyse_people_{column}", "analyse_people", [column])
    op.create_table(
        "analyse_access_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _analyse(),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("author_id", sa.String(), nullable=True),
        _timestamp(),
    )
    op.create_index("ix_analyse_access_versions_analyse_id", "analyse_access_versions", ["analyse_id"])
    op.execute(
        "INSERT INTO analyse_groups (analyse_id, group_id) "
        "SELECT DISTINCT s.analyse_id, s.keycloak_group FROM analyse_shares s "
        "JOIN app_groups g ON g.id::text = s.keycloak_group"
    )


def downgrade() -> None:
    for table in ("analyse_access_versions", "analyse_people", "analyse_groups"):
        op.drop_table(table)
