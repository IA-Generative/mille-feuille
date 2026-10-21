import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class TokenUsageKind(enum.StrEnum):
    CHAT = "chat"
    EMBEDDING = "embedding"


class TokenUsage(UUIDMixin, TimestampMixin, Base):
    """Un appel au LLM : ceux des workers (déposés par `POST /internal/usage`) et ceux du backend (aide LLM du
    frontend). **Que des compteurs** : jamais le prompt, la réponse ni le contenu d'un document.

    `step` dit à quoi servait l'appel (tâche du worker : classify_dossier, run_chat...). `user_id` est la personne pour
    qui l'appel a été fait, quand le worker la connaît ; NULL sinon (classification et extraction d'un dossier
    n'ont pas d'auteur). `dossier_id` est un simple identifiant, sans clé étrangère : la consommation est un
    historique, elle survit à la suppression du dossier."""

    __tablename__ = "token_usages"

    user_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    step: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[TokenUsageKind] = mapped_column(Enum(TokenUsageKind, name="token_usage_kind"), nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dossier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Redéfini pour l'indexer : chaque rapport filtre sur une période.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
