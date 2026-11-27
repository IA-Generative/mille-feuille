"""Qui voit une analyse (issue #662) : ses groupes, et des personnes ajoutées."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.encrypted import EncryptedString, EncryptedText


class AnalyseGroup(TimestampMixin, Base):
    """``group_id`` : identifiant d'un groupe de l'application, en texte (comme `dossier_group_access`)."""

    __tablename__ = "analyse_groups"

    analyse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    granted_by: Mapped[str | None] = mapped_column(String, nullable=True)


class AnalysePerson(UUIDMixin, TimestampMixin, Base):
    """Une personne ajoutée à une analyse, avec un rôle limité à celle-ci. `user_id` vide : pas encore rattachée."""

    __tablename__ = "analyse_people"
    __table_args__ = (
        UniqueConstraint("analyse_id", "user_id", name="ux_analyse_people_user"),
        UniqueConstraint("analyse_id", "email_index", name="ux_analyse_people_email"),
        CheckConstraint("user_id IS NOT NULL OR email_index IS NOT NULL", name="ck_analyse_people_identity"),
    )

    analyse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("app_roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    email_index: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    added_by: Mapped[str | None] = mapped_column(String, nullable=True)


class AnalyseAccessVersion(UUIDMixin, TimestampMixin, Base):
    """Les accès tels qu'ils étaient juste avant un changement (restaurables). Le contenu, un JSON, porte des
    adresses : il est chiffré en entier."""

    __tablename__ = "analyse_access_versions"

    analyse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    author_id: Mapped[str | None] = mapped_column(String, nullable=True)
