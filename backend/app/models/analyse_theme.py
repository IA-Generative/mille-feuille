import uuid

from sqlalchemy import ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class AnalyseTheme(UUIDMixin, TimestampMixin, Base):
    """Un thème range des analyses (sécurité routière, CNAPS...) : une analyse appartient à un thème au plus. Il ne
    change aucun droit d'accès. Géré par les administrateurs."""

    __tablename__ = "analyse_themes"

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)

    versions: Mapped[list["AnalyseThemeVersion"]] = relationship(
        cascade="all, delete-orphan", order_by="AnalyseThemeVersion.created_at.desc()", lazy="selectin"
    )


# Deux thèmes ne diffèrent pas que par la casse.
Index("ux_analyse_themes_lower_name", func.lower(AnalyseTheme.name), unique=True)


class AnalyseThemeVersion(UUIDMixin, TimestampMixin, Base):
    """Ancienne valeur du nom ou de la description d'un thème, prise juste avant son remplacement (restaurable)."""

    __tablename__ = "analyse_theme_versions"

    theme_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analyse_themes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "name" ou "description".
    field: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
