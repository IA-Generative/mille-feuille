import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.encrypted import EncryptedText


class Notification(UUIDMixin, TimestampMixin, Base):
    """Notification d'une personne sur un dossier (issue #174) : on lui a affecté un dossier, l'échéance approche,
    le statut a changé par un tiers, une analyse qu'elle a lancée est finie.

    **Propre au destinataire** : elle seule la lit et la marque comme lue. Elle ne contient que des noms et des
    valeurs d'affichage (jamais le contenu du dossier). ``dedup_key`` garantit **une seule notification par fait**
    (un événement du journal, un seuil d'échéance franchi) même si deux lectures la produisent en même temps."""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedup_key", name="uq_notifications_user_dedup"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # assigned, due_soon, overdue, status_changed, analysis_done, analysis_failed (puis reminder, avec les rappels).
    kind: Mapped[str] = mapped_column(String, nullable=False)
    # Le dossier disparu emporte ses notifications.
    dossier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nom du dossier au moment de la notification (photographie, pour l'afficher sans jointure).
    dossier_name: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    dedup_key: Mapped[str] = mapped_column(String, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationCursor(Base):
    """Jusqu'où le journal a été lu pour une personne : les notifications se fabriquent **à la lecture**, à partir
    des événements du journal (#169) postérieurs à ce curseur (``last_seq``, cf. ``DossierEvent.seq``)."""

    __tablename__ = "notification_cursors"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    last_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
