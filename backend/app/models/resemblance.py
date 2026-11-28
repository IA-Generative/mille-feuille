"""Thèmes de ressemblance entre dossiers (#649) et ce que leur calcul trouve."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.encrypted import EncryptedString


class ResemblanceTheme(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "resemblance_themes"

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    # "all", "within" (au sein d'un thème d'analyse) ou "across" (entre thèmes d'analyse).
    scope: Mapped[str] = mapped_column(String, nullable=False)
    # "identical", "probable" ou "to_check" : ce que l'administrateur annonce.
    certainty: Mapped[str] = mapped_column(String, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # [{"id", "origin": "analysis"|"file", "name", "entity_ids": [], "refused_ids": []}], tous obligatoires.
    criteria: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list["ResemblanceThemeVersion"]] = relationship(
        cascade="all, delete-orphan", order_by="ResemblanceThemeVersion.created_at.desc()", lazy="selectin"
    )


class ResemblanceThemeVersion(UUIDMixin, TimestampMixin, Base):
    """L'état d'un thème juste avant son remplacement (restaurable)."""

    __tablename__ = "resemblance_theme_versions"

    theme_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("resemblance_themes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)


class ResemblanceMember(Base):
    """Un dossier d'un groupe trouvé. Aucune valeur n'est copiée ici : les preuves sont relues à l'affichage."""

    __tablename__ = "resemblance_members"

    theme_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("resemblance_themes.id", ondelete="CASCADE"), primary_key=True
    )
    # Empreinte de ce que le groupe a en commun.
    group_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    dossier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class ResemblanceDismissal(UUIDMixin, TimestampMixin, Base):
    """Un rapprochement écarté comme faux. La ligne reste après rétablissement : c'est la trace."""

    __tablename__ = "resemblance_dismissals"

    theme_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("resemblance_themes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_key: Mapped[str] = mapped_column(String(64), nullable=False)
    dismissed_by: Mapped[str] = mapped_column(String, nullable=False)
    dismissed_by_name: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    restored_by: Mapped[str | None] = mapped_column(String, nullable=True)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
