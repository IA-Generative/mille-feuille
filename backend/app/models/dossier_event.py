import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin
from app.models.encrypted import EncryptedPeopleJSON, EncryptedString


class DossierEventType(enum.StrEnum):
    """Types d'événements du journal d'un dossier (issue #169). Le type est stocké en texte, pas en enum
    PostgreSQL : en ajouter un (échéance #172, affectation #173, accès #177…) ne demande pas de migration."""

    CREATED = "created"
    CONSULTED = "consulted"
    STATUS_CHANGED = "status_changed"
    DUE_DATE_CHANGED = "due_date_changed"
    # Affecté, réaffecté ou désaffecté (issue #173) ; `from` / `to` : {id, name} ou null.
    ASSIGNEE_CHANGED = "assignee_changed"
    # Visibilité ou groupes d'accès modifiés (issue #177) : ``visibility`` {from, to}, ``groups_added``,
    # ``groups_removed``.
    # Valeur d'une colonne personnalisée modifiée (issue #173) : ``field`` {id, name}, ``from``, ``to``.
    CUSTOM_VALUE_CHANGED = "custom_value_changed"
    ACCESS_CHANGED = "access_changed"
    # Un administrateur est entré dans un dossier restreint dont il n'est pas membre d'un groupe (issue #182). Réservé
    # à la lecture des administrateurs ; ``method`` : verbe HTTP, ``write`` : vrai pour une modification.
    ADMIN_ACCESS = "admin_access"
    # Le dossier entre dans un statut final (date de clôture posée) / en sort (réouverture).
    CLOSED = "closed"
    REOPENED = "reopened"
    ANALYSE_ASSIGNED = "analyse_assigned"
    DOCUMENT_ADDED = "document_added"
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_STOPPED = "analysis_stopped"
    ANALYSIS_FINISHED = "analysis_finished"
    ANALYSIS_FAILED = "analysis_failed"
    DOCUMENT_GENERATED = "document_generated"
    DOCUMENT_DOWNLOADED = "document_downloaded"


class DossierEvent(UUIDMixin, Base):
    """Une ligne du journal d'un dossier : qui a fait quoi, et quand. **Append-only** : l'application n'expose
    aucune modification ni suppression ; les lignes ne partent qu'avec leur dossier (cascade, cf. #94).

    ``payload`` ne contient que les valeurs nécessaires (ancienne et nouvelle valeur, identifiants) : jamais le
    contenu du dossier (données d'usagers) ni un nom de fichier déposé."""

    __tablename__ = "dossier_events"
    __table_args__ = (Index("ix_dossier_events_dossier_id_seq", "dossier_id", "seq"),)

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Identifiant (sub Keycloak) de l'auteur ; NULL pour une action du système (fin d'analyse par un worker).
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Nom affiché de l'auteur au moment de l'événement (photographie : l'annuaire est dans Keycloak).
    actor_name: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Ordre d'écriture, strictement croissant : plusieurs événements d'une même transaction ont le même
    # `created_at` (now() est l'heure de la transaction), `seq` les départage dans l'ordre où ils ont eu lieu.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False)
    payload: Mapped[dict] = mapped_column(EncryptedPeopleJSON, nullable=False, default=dict)
