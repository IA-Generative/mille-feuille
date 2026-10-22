import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ToolAuthMode(enum.StrEnum):
    """Comment la plateforme s'authentifie auprès d'un serveur MCP. `static_token` existe dans le modèle mais n'est
    pas encore activable (l'API le refuse) ; voir docs/tools-mcp-plan.md."""

    NONE = "none"
    TOKEN_EXCHANGE = "token_exchange"
    STATIC_TOKEN = "static_token"


class ToolVisibility(enum.StrEnum):
    PRIVATE = "private"
    GROUPS = "groups"
    ALL = "all"


class ToolServer(UUIDMixin, TimestampMixin, Base):
    """Un serveur MCP ajouté par une personne : la plateforme en est cliente. Ses tools sont importés (`tools/list`)
    et rattachés ici ; les tools internes ne sont pas en base (voir services/tools/internal_catalog.py)."""

    __tablename__ = "tool_servers"

    name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    auth_mode: Mapped[ToolAuthMode] = mapped_column(Enum(ToolAuthMode, name="tool_auth_mode"), nullable=False)
    visibility: Mapped[ToolVisibility] = mapped_column(
        Enum(ToolVisibility, name="tool_visibility"), nullable=False, default=ToolVisibility.PRIVATE
    )
    # Identifiant Keycloak de la personne qui l'a ajouté, et son nom d'affichage au moment de l'ajout.
    created_by: Mapped[str] = mapped_column(String, nullable=False, index=True)
    owner_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    # Groupes de la personne au moment de l'ajout : ceux qui voient le serveur quand `visibility` vaut `groups`.
    groups: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Client Keycloak du serveur : l'`audience` demandée à l'échange de jeton (mode `token_exchange`).
    audience: Mapped[str | None] = mapped_column(String, nullable=True)
    # Secret d'un `static_token`, chiffré. Toujours vide tant que ce mode n'est pas activable.
    credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tools: Mapped[list["Tool"]] = relationship(
        back_populates="server", cascade="all, delete-orphan", order_by="Tool.name", lazy="selectin"
    )


class Tool(UUIDMixin, TimestampMixin, Base):
    """Un tool importé d'un serveur MCP. `enabled` : la personne qui a ajouté le serveur l'autorise (elle choisit ceux
    qu'elle importe) ; les agents en retiennent ensuite une partie."""

    __tablename__ = "tools"
    __table_args__ = (UniqueConstraint("server_id", "name", name="uq_tools_server_id_name"),)

    server_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tool_servers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Le tool modifie des données : le chat demande une confirmation avant l'appel. Déduit de l'annotation MCP
    # `readOnlyHint` ; sans elle, on suppose que le tool modifie (prudence).
    side_effect: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    server: Mapped["ToolServer"] = relationship(back_populates="tools")
