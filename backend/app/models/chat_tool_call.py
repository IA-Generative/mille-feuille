import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.conversation import Message


class ChatToolCallStatus(enum.StrEnum):
    # Le modèle veut appeler un outil qui modifie des données : on attend la décision de la personne.
    PENDING = "pending"
    # Autorisé : le worker l'exécute au début de la prochaine exécution du chat.
    APPROVED = "approved"
    REFUSED = "refused"
    # Exécuté (tout de suite pour un outil en lecture seule, après autorisation sinon) : `result` est renseigné.
    EXECUTED = "executed"
    # La personne a écrit un autre message avant de décider : l'appel n'a pas été fait.
    SUPERSEDED = "superseded"


class ChatToolCall(UUIDMixin, TimestampMixin, Base):
    """Un appel d'outil du modèle, gardé avec le message de l'assistant qui le porte. C'est l'**historique** de la
    discussion qui sert d'état : une demande de confirmation n'attend pas, la tâche se termine ; la personne décide
    quand elle veut, et la prochaine exécution reconstruit la discussion avec l'appel et son résultat.

    Les appels d'un même tour (jusqu'à 5) forment un lot : ils partagent `message_id`, et se décident ensemble."""

    __tablename__ = "chat_tool_calls"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # L'ordre dans le tour du modèle.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # L'identifiant de l'appel côté modèle (rejoué tel quel dans l'historique) et le nom de la fonction qu'il a appelée.
    llm_call_id: Mapped[str] = mapped_column(String, nullable=False)
    function_name: Mapped[str] = mapped_column(String, nullable=False)
    # Le tool exécuté (identifiant d'un tool MCP), et de quoi l'afficher à la personne.
    tool_id: Mapped[str] = mapped_column(String, nullable=False)
    tool_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    server_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    # Les arguments choisis par le modèle : ce sont **exactement ceux** que la personne voit et que l'exécution utilise.
    arguments: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    side_effect: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[ChatToolCallStatus] = mapped_column(
        Enum(ChatToolCallStatus, name="chat_tool_call_status"), nullable=False, default=ChatToolCallStatus.PENDING
    )
    # Ce que le modèle lira comme réponse de l'outil (sortie, refus, « sans réponse »).
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    message: Mapped["Message"] = relationship(back_populates="tool_calls")
