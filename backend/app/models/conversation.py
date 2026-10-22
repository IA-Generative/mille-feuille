import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Enum, ForeignKey, String, Table, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.chat_event import ChatEvent
    from app.models.chat_tool_call import ChatToolCall
    from app.models.document_page import BoundingBox, DocumentPage
    from app.models.dossier import Dossier, DossierDocument, ExecutionStep
    from app.models.feedback import Feedback

# Granularité d'une source, du plus large au plus précis : au minimum le
# document (dossier_document_id ci-dessous), éventuellement affinée à un
# ensemble de pages, ou plus précisément à un ensemble de bbox sur ces pages.
message_source_pages = Table(
    "message_source_pages",
    Base.metadata,
    Column(
        "message_source_id",
        PG_UUID(as_uuid=True),
        ForeignKey("message_sources.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "document_page_id",
        PG_UUID(as_uuid=True),
        ForeignKey("document_pages.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

message_source_bounding_boxes = Table(
    "message_source_bounding_boxes",
    Base.metadata,
    Column(
        "message_source_id",
        PG_UUID(as_uuid=True),
        ForeignKey("message_sources.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "bounding_box_id",
        PG_UUID(as_uuid=True),
        ForeignKey("bounding_boxes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Conversation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("dossier_id", "user_id", name="uq_conversations_dossier_id_user_id"),)

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("dossiers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # L'auteur de la conversation (identité Keycloak) : la page dossier est
    # un chat personnel à chaque instructeur qui l'ouvre.
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Identifiant de modèle LLM tel que renvoyé par GET /models ; None = pas
    # de préférence, le hub par défaut sera utilisé.
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    # Les outils que la personne a **retirés** pour cette conversation (identifiants). Tout ce que l'analyse autorise
    # est actif par défaut : elle ne peut que retirer, jamais ajouter un outil que l'analyse n'autorise pas.
    excluded_tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    dossier: Mapped["Dossier"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    chat_events: Mapped[list["ChatEvent"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatEvent.created_at",
    )

    @property
    def dossier_name(self) -> str:
        return self.dossier.name if self.dossier else ""

    @property
    def last_message_preview(self) -> str | None:
        if not self.messages:
            return None
        return self.messages[-1].content

    @property
    def last_activity_at(self) -> datetime:
        if self.messages:
            return self.messages[-1].created_at
        return self.created_at


class Message(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole, name="message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    sources: Mapped[list["MessageSource"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="MessageSource.created_at",
    )
    feedbacks: Mapped[list["Feedback"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="Feedback.created_at",
    )
    # Les appels d'outils du modèle portés par ce message (un lot, jusqu'à 5), avec leur décision et leur résultat.
    tool_calls: Mapped[list["ChatToolCall"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="ChatToolCall.position",
    )

    @property
    def feedback(self) -> "Feedback | None":
        """Le retour de l'utilisateur courant, positionne par le routeur
        avant serialisation (MessageOut.feedback). None tant que le routeur
        n'a pas filtre les feedbacks par user_id."""
        return getattr(self, "_feedback", None)

    @feedback.setter
    def feedback(self, value: "Feedback | None") -> None:
        self._feedback = value


class MessageSource(UUIDMixin, TimestampMixin, Base):
    """Référence utilisée par l'agent pour construire une réponse : un
    document (et éventuellement une étape d'exécution), avec un court
    extrait pour donner le contexte sans rouvrir le document entier."""

    __tablename__ = "message_sources"

    message_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dossier_document_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("dossier_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    execution_step_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("execution_steps.id", ondelete="SET NULL"),
        nullable=True,
    )
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    message: Mapped["Message"] = relationship(back_populates="sources")
    document: Mapped["DossierDocument | None"] = relationship()
    execution_step: Mapped["ExecutionStep | None"] = relationship()
    pages: Mapped[list["DocumentPage"]] = relationship(
        secondary=message_source_pages, order_by="DocumentPage.page_number"
    )
    bounding_boxes: Mapped[list["BoundingBox"]] = relationship(
        secondary=message_source_bounding_boxes, order_by="BoundingBox.created_at"
    )
