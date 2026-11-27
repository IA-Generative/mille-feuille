"""groupes, rôles et membres de l'application

Revision ID: f3b5d7e9a1c2
Revises: e2a4c6b8d0f1
Create Date: 2026-11-27 19:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f3b5d7e9a1c2"
down_revision = "e2a4c6b8d0f1"
branch_labels = None
depends_on = None


def _id() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)


def _timestamp() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def _reference(name: str, table: str, ondelete: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name, postgresql.UUID(as_uuid=True), sa.ForeignKey(f"{table}.id", ondelete=ondelete), nullable=nullable
    )


def upgrade() -> None:
    op.create_table(
        "app_groups",
        _id(),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(), nullable=True),
        _timestamp(),
    )
    op.create_index("ux_app_groups_lower_name", "app_groups", [sa.text("lower(name)")], unique=True)
    roles = op.create_table(
        "app_roles",
        _id(),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("permissions", postgresql.JSONB(), nullable=False),
        sa.Column("system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_by", sa.String(), nullable=True),
        _timestamp(),
    )
    op.create_index("ux_app_roles_lower_name", "app_roles", [sa.text("lower(name)")], unique=True)
    op.create_table(
        "access_versions",
        _id(),
        _reference("group_id", "app_groups", "CASCADE", nullable=True),
        _reference("role_id", "app_roles", "CASCADE", nullable=True),
        sa.Column("field", sa.String(), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("author_id", sa.String(), nullable=True),
        _timestamp(),
        sa.CheckConstraint("(group_id IS NULL) <> (role_id IS NULL)", name="ck_access_versions_owner"),
    )
    op.create_index("ix_access_versions_group_id", "access_versions", ["group_id"])
    op.create_index("ix_access_versions_role_id", "access_versions", ["role_id"])
    op.create_table(
        "app_group_members",
        _id(),
        _reference("group_id", "app_groups", "CASCADE"),
        _reference("role_id", "app_roles", "RESTRICT"),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("email_index", sa.String(), nullable=True),
        sa.Column("added_by", sa.String(), nullable=True),
        _timestamp(),
        sa.UniqueConstraint("group_id", "user_id", name="ux_app_group_members_user"),
        sa.UniqueConstraint("group_id", "email_index", name="ux_app_group_members_email"),
        sa.CheckConstraint("user_id IS NOT NULL OR email_index IS NOT NULL", name="ck_app_group_members_identity"),
    )
    for column in ("group_id", "role_id", "user_id", "email_index"):
        op.create_index(f"ix_app_group_members_{column}", "app_group_members", [column])
    op.create_table(
        "app_group_events",
        _id(),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("actor_name", sa.String(), nullable=True),
        sa.Column("subject_user_id", sa.String(), nullable=True),
        sa.Column("subject_email", sa.String(), nullable=True),
        sa.Column("role_name", sa.String(), nullable=True),
        sa.Column("previous_role_name", sa.String(), nullable=True),
        _timestamp(),
    )
    op.create_index("ix_app_group_events_group_id", "app_group_events", ["group_id"])

    # Les rôles de la maquette. Les listes sont figées ici : une migration ne suit pas le code.
    instructor = ["dossier.view", "dossier.edit", "dossier.run", "dossier.validate", "dossier.generate"]
    every = [*instructor, "dossier.delete", "analyse.create", "analyse.configure", "analyse.access", "group.members"]
    op.bulk_insert(
        roles,
        [
            {
                "id": f"00000000-0000-4000-8000-00000000000{number}",
                "name": name,
                "description": description,
                "permissions": permissions,
                "system": system,
            }
            for number, name, description, permissions, system in (
                (1, "Admin de groupe", "Toutes les permissions sur son groupe.", every, True),
                (2, "Instructeur", "Instruit les dossiers.", instructor, False),
                (3, "Lecteur", "Consulte sans modifier.", ["dossier.view"], False),
            )
        ],
    )


def downgrade() -> None:
    for table in ("app_group_events", "app_group_members", "access_versions", "app_roles", "app_groups"):
        op.drop_table(table)
