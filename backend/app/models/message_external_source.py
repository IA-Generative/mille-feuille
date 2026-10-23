import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.conversation import Message


class MessageExternalSource(UUIDMixin, TimestampMixin, Base):
    """Une source d'une base de connaissances externe citée par un message de l'assistant : un passage d'un document ou
    d'un site web, avec de quoi l'afficher (lien, aperçu, zones). À la différence d'une `MessageSource`, elle ne
    référence aucun document du dossier : tout est recopié ici, tel que le fournisseur l'a renvoyé au moment de la
    réponse (la source peut changer ou disparaître ensuite, la réponse garde ce qui la fondait)."""

    __tablename__ = "message_external_sources"

    message_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # L'ordre de dépôt, et le numéro que le modèle a cité dans sa réponse ([2]) : une seule suite avec les sources du
    # dossier (`MessageSource.number`). Le numéro est vide pour les messages d'avant.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # L'identifiant du passage chez le fournisseur.
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    preview_url: Mapped[str | None] = mapped_column(String, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Les zones à surligner : [{page, x_min, y_min, x_max, y_max}], coordonnées normalisées 0..1. Peut être vide.
    boxes: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    passage: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    collection_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    collection_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    source_name: Mapped[str] = mapped_column(String, nullable=False, default="")

    message: Mapped["Message"] = relationship(back_populates="external_sources")
