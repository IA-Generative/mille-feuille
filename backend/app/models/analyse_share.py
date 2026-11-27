import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.encrypted import EncryptedString

if TYPE_CHECKING:
    from app.models.analyse import Analyse


class AnalyseShareKind(enum.StrEnum):
    EMAIL = "email"
    KEYCLOAK_GROUP = "keycloak_group"


class AnalyseShare(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "analyse_shares"

    analyse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[AnalyseShareKind] = mapped_column(Enum(AnalyseShareKind, name="analyse_share_kind"), nullable=False)
    # kind == EMAIL :
    email: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    # Hash du jeton du lien magique (jamais le jeton lui-même : une fuite de
    # la base ne doit pas suffire à usurper le partage). Voir
    # AnalyseShareRepository.hash_token.
    token_hash: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # kind == KEYCLOAK_GROUP :
    keycloak_group: Mapped[str | None] = mapped_column(String, nullable=True)

    created_by: Mapped[str] = mapped_column(String, nullable=False)

    analyse: Mapped["Analyse"] = relationship(back_populates="shares")
