import enum
import uuid

from sqlalchemy import Enum, Float, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.document_page import PredictionKind, PredictionSource


class EphemeralVerdict(enum.StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"


class EphemeralFeedback(UUIDMixin, TimestampMixin, Base):
    """Verdict d'un appelant sur une prédiction d'un run éphémère (classification d'une page, entité) : bonne ou
    mauvaise. Sert à calculer des métriques (précision par source, par label/entité, confusions).

    Pas de FK vers le run ni la prédiction : le dossier d'un run `persist=false` est supprimé à sa fin, ses
    prédictions avec. On garde donc de quoi calculer les métriques (méthode, nom, confiance) et **jamais la valeur
    extraite** (une entité peut être une donnée personnelle, et le run est éphémère par définition). Un verdict reste
    tant que l'appelant ne le supprime pas."""

    __tablename__ = "ephemeral_feedback"
    __table_args__ = (UniqueConstraint("run_id", "prediction_id", "created_by", name="uq_ephemeral_feedback_verdict"),)

    run_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    prediction_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    # Même rôle que DossierEphemere.created_by : l'identité de l'appelant (compte, jeton ou clé d'environnement).
    created_by: Mapped[str] = mapped_column(String, nullable=False, index=True)

    kind: Mapped[PredictionKind] = mapped_column(Enum(PredictionKind, name="prediction_kind", create_type=False))
    # Nom du label ou de l'entité prédit (pas sa valeur).
    name: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[PredictionSource] = mapped_column(
        Enum(PredictionSource, name="prediction_source", create_type=False)
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    verdict: Mapped[EphemeralVerdict] = mapped_column(Enum(EphemeralVerdict, name="ephemeral_verdict"), nullable=False)
    # Pour un label jugé incorrect : le label qui était attendu (alimente la matrice de confusion).
    expected_name: Mapped[str | None] = mapped_column(String, nullable=True)
