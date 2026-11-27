import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Visibility(enum.StrEnum):
    """Qui voit un dossier (issue #177)."""

    # Seuls les membres des groupes associés (et les administrateurs).
    RESTRICTED = "restricted"
    # Tout utilisateur qui a accès à l'analyse (comportement historique, gardé pour les dossiers existants).
    ANALYSE = "analyse"


class DossierGroupAccess(Base):
    """Un groupe qui a accès à un dossier restreint (issue #177).

    ``group_id`` est l'identifiant d'un groupe de l'application (``app_groups.id``), en texte : pas d'héritage entre
    groupes. Le créateur du dossier n'a aucun droit propre : son accès vient de ses groupes, comme celui de tout le
    monde."""

    __tablename__ = "dossier_group_access"
    __table_args__ = (Index("ix_dossier_group_access_group", "group_id"),)

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[str] = mapped_column(String, primary_key=True)
    # Qui a associé le groupe (sub Keycloak), pour l'historique.
    granted_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
