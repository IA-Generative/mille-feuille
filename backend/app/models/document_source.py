import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class DocumentSource(UUIDMixin, TimestampMixin, Base):
    """D'où vient un fichier déposé dans un dossier (courrier, guichet, autre administration…) : libre, définie
    par l'utilisateur, avec une description que l'IA reçoit en contexte.

    Une source appartient à **une analyse** (catalogue de l'analyse, proposée pour tous ses dossiers) **ou** à **un
    dossier** (source « tampon » : créée depuis un dossier « à ranger », qui n'a pas encore d'analyse). Au
    rattachement du dossier à une analyse, ses sources tampon rejoignent le catalogue de l'analyse. Pas de
    versionnage (décision explicite). Supprimer une source laisse ses documents, sans source."""

    __tablename__ = "document_sources"

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    analyse_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=True, index=True
    )
    dossier_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=True, index=True
    )

    __table_args__ = (
        # Exactement un propriétaire : l'analyse (catalogue) ou le dossier (tampon).
        CheckConstraint("(analyse_id IS NULL) <> (dossier_id IS NULL)", name="ck_document_source_one_owner"),
        # Un nom par catalogue d'analyse, et un par dossier pour les sources tampon.
        Index(
            "uq_document_source_analyse_name",
            "analyse_id",
            "name",
            unique=True,
            postgresql_where=text("analyse_id IS NOT NULL"),
        ),
        Index(
            "uq_document_source_dossier_name",
            "dossier_id",
            "name",
            unique=True,
            postgresql_where=text("dossier_id IS NOT NULL"),
        ),
    )
