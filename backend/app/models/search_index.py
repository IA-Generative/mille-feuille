import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class SearchIndexStatus(enum.StrEnum):
    # Des passages sont en cours d'écriture ; la recherche répond déjà avec ce qui est indexé.
    INDEXING = "indexing"
    READY = "ready"
    ERROR = "error"


class DossierSearchIndex(TimestampMixin, Base):
    """L'index de recherche actif d'un dossier (Qdrant, alias `dossier_<id>`) : avec quels réglages il a été construit.

    Les réglages sont **ceux de l'index**, pas ceux de l'analyse : un document ajouté plus tard est indexé comme le
    reste du dossier, même si l'analyse a changé depuis. Quand l'empreinte de l'analyse diffère de celle-ci, l'index est
    obsolète et peut être reconstruit (`IndexRebuild`)."""

    __tablename__ = "dossier_search_indexes"

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE"), primary_key=True
    )
    fingerprint: Mapped[str] = mapped_column(String, nullable=False)
    # Réglages effectifs (stratégie, modèles, paramètres) qui ont produit l'empreinte.
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[SearchIndexStatus] = mapped_column(
        Enum(SearchIndexStatus, name="search_index_status"), nullable=False, default=SearchIndexStatus.INDEXING
    )
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IndexRebuildStatus(enum.StrEnum):
    # Le nouvel index se construit à côté de l'actif, qui continue de répondre à toutes les recherches.
    BUILDING = "building"
    # Le nouvel index a remplacé l'ancien, atomiquement ; l'ancien est gardé jusqu'à validation ou retour arrière.
    SWAPPED = "swapped"
    FINALIZED = "finalized"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


# Un dossier a au plus une reconstruction dans ces états : elle détient son second index.
ACTIVE_REBUILD_STATUSES = (IndexRebuildStatus.BUILDING, IndexRebuildStatus.SWAPPED)


class IndexRebuild(UUIDMixin, TimestampMixin, Base):
    """Reconstruction blue/green de l'index d'un dossier avec de nouveaux réglages."""

    __tablename__ = "index_rebuilds"

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[IndexRebuildStatus] = mapped_column(
        Enum(IndexRebuildStatus, name="index_rebuild_status"), nullable=False
    )
    target_fingerprint: Mapped[str] = mapped_column(String, nullable=False)
    target_settings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    previous_fingerprint: Mapped[str | None] = mapped_column(String, nullable=True)
    previous_settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    total_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    done_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str] = mapped_column(String, nullable=False)
    swapped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "uq_index_rebuilds_active_per_dossier",
            "dossier_id",
            unique=True,
            postgresql_where=text("status IN ('BUILDING', 'SWAPPED')"),
        ),
    )
