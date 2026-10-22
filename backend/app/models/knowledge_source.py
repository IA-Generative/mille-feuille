from sqlalchemy import Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.tool import ToolAuthMode, ToolVisibility


class KnowledgeSource(UUIDMixin, TimestampMixin, Base):
    """Un fournisseur de collections branché sur la plateforme : une URL qui respecte le contrat
    docs/backend/base-de-connaissances-api.yaml (les collections sont choisies ensuite par analyse). Authentification et
    visibilité suivent exactement celles des serveurs MCP (`ToolAuthMode`, `ToolVisibility`, services/tools)."""

    __tablename__ = "knowledge_sources"

    name: Mapped[str] = mapped_column(String, nullable=False)
    # L'adresse de base de l'API : les routes du contrat (`/v1/collections`…) s'y ajoutent.
    url: Mapped[str] = mapped_column(String, nullable=False)
    auth_mode: Mapped[ToolAuthMode] = mapped_column(
        Enum(ToolAuthMode, name="tool_auth_mode", create_type=False), nullable=False
    )
    visibility: Mapped[ToolVisibility] = mapped_column(
        Enum(ToolVisibility, name="tool_visibility", create_type=False), nullable=False, default=ToolVisibility.PRIVATE
    )
    # Identifiant Keycloak de la personne qui l'a ajoutée, et son nom d'affichage au moment de l'ajout.
    created_by: Mapped[str] = mapped_column(String, nullable=False, index=True)
    owner_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    # Groupes de la personne au moment de l'ajout : ceux qui voient la source quand `visibility` vaut `groups`.
    groups: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Client Keycloak du fournisseur : l'`audience` demandée à l'échange de jeton (mode `token_exchange`).
    audience: Mapped[str | None] = mapped_column(String, nullable=True)
    # Secret d'un `static_token`, chiffré. Toujours vide tant que ce mode n'est pas activable.
    credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
