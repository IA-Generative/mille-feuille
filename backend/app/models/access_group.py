"""Groupes, rôles et membres de l'application (issue #659)."""

import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.encrypted import EncryptedString


class AppGroup(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "app_groups"

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    # Chemin du groupe Keycloak dont ce groupe est la reprise (issue #663).
    keycloak_path: Mapped[str | None] = mapped_column(String, nullable=True)

    versions: Mapped[list["AccessVersion"]] = relationship(
        cascade="all, delete-orphan", order_by="AccessVersion.created_at.desc()", lazy="selectin"
    )


class AppRole(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "app_roles"

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    # Valeurs de `app.services.permissions.Permission`.
    permissions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Rôle fourni et figé : ni modifiable ni supprimable, et toutes les permissions.
    system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)

    versions: Mapped[list["AccessVersion"]] = relationship(
        cascade="all, delete-orphan", order_by="AccessVersion.created_at.desc()", lazy="selectin"
    )


# Deux groupes, ou deux rôles, ne diffèrent pas que par la casse.
Index("ux_app_groups_lower_name", func.lower(AppGroup.name), unique=True)
Index("ux_app_roles_lower_name", func.lower(AppRole.name), unique=True)


class AccessVersion(UUIDMixin, TimestampMixin, Base):
    """Ancienne valeur d'un champ d'un groupe ou d'un rôle, prise juste avant son remplacement (restaurable)."""

    __tablename__ = "access_versions"
    __table_args__ = (CheckConstraint("(group_id IS NULL) <> (role_id IS NULL)", name="ck_access_versions_owner"),)

    group_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("app_groups.id", ondelete="CASCADE"), nullable=True, index=True
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("app_roles.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # "name", "description" ou "permissions".
    field: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[object] = mapped_column(JSONB, nullable=False)
    author_id: Mapped[str | None] = mapped_column(String, nullable=True)


class AppGroupMember(UUIDMixin, TimestampMixin, Base):
    """Une personne dans un groupe, avec son rôle. `user_id` vide : pas encore rattachée à un compte, seule son adresse
    est connue (le rattachement à la première connexion vient avec l'issue #660)."""

    __tablename__ = "app_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="ux_app_group_members_user"),
        UniqueConstraint("group_id", "email_index", name="ux_app_group_members_email"),
        CheckConstraint("user_id IS NOT NULL OR email_index IS NOT NULL", name="ck_app_group_members_identity"),
    )

    group_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("app_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("app_roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    email_index: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    added_by: Mapped[str | None] = mapped_column(String, nullable=True)


class AppGroupEventType(enum.StrEnum):
    GROUP_CREATED = "group_created"
    GROUP_UPDATED = "group_updated"
    GROUP_DELETED = "group_deleted"
    MEMBER_ADDED = "member_added"
    MEMBER_ROLE_CHANGED = "member_role_changed"
    MEMBER_REMOVED = "member_removed"


class AppGroupEvent(UUIDMixin, TimestampMixin, Base):
    """Journal d'un groupe : qui a fait quoi, quand. Sans clé étrangère : il survit au groupe."""

    __tablename__ = "app_group_events"

    group_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_name: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    # La personne concernée par un changement de membre.
    subject_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    subject_email: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    role_name: Mapped[str | None] = mapped_column(String, nullable=True)
    previous_role_name: Mapped[str | None] = mapped_column(String, nullable=True)
