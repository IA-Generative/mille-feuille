import uuid
from typing import Any

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class EphemeralRunMetrics(TimestampMixin, Base):
    """Condensé **non sensible** d'un run éphémère, conservé après la purge de son résultat : de quoi calculer des
    métriques par `run_id` (volumes, confiances, accord entre méthodes, durées) et rattacher des verdicts.

    Il contient les noms des labels et entités (ceux de l'analyse), la méthode (`source`), la confiance, le numéro de
    page, le statut et les durées. **Jamais** le contenu des documents, ni les valeurs extraites, ni les noms de
    fichiers : un run est éphémère justement parce que son contenu peut être sensible. Supprimé après
    EPHEMERAL_METRICS_RETENTION_DAYS jours (voir app.tasks.run_purge), ou à la demande."""

    __tablename__ = "ephemeral_run_metrics"

    run_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Durée du run en secondes (ended_at - started_at), NULL tant qu'il n'est pas terminé.
    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)
    # [{kind, status, duration_seconds}] : une entrée par étape d'exécution (jamais son libellé ni sa sortie).
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # [{id, kind, name, source, confidence, page_number}] : une entrée par prédiction (id de la prédiction).
    predictions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
