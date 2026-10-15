import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class EphemeralResult(TimestampMixin, Base):
    """Résultat conservé d'un run éphémère (persist=false) une fois celui-ci
    terminé : instantané JSON de ce que renvoie GET /api/ephemeral/runs/{id}.

    À la fin du run, le Dossier (documents, fichiers S3, étapes, prédictions)
    et l'analyse éphémère sont supprimés ; seule cette ligne reste, jusqu'à
    `expires_at` (ended_at + ttl_hours), puis la purge la supprime à son tour.
    Pas de FK vers Dossier : c'est justement lui qui disparaît."""

    __tablename__ = "ephemeral_results"

    run_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    # Même rôle que DossierEphemere.created_by : scoping de visibilité.
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # Captures de pages conservées jusqu'à `expires_at` (id de page -> clé S3), pour afficher les zones des résultats
    # sur la page : seules ces images survivent à la fin du run, le fichier d'origine est supprimé. Jamais exposé tel
    # quel : l'image se lit via GET /api/ephemeral/runs/{run_id}/pages/{page_id}/screenshot.
    screenshot_keys: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
