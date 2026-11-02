"""Réponses prêtes aux questions fréquentes d'une analyse (issue #422).

Une ligne par dossier et par question de l'analyse (`Analyse.frequent_questions`). Elle est calculée à la fin de
l'analyse du dossier ; `fingerprint` résume ce qu'elle a lu, pour qu'une réponse à jour ne soit jamais recalculée."""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class QuestionAnswerStatus(enum.StrEnum):
    EN_COURS = "en_cours"
    REPONDUE = "répondue"
    # Le dossier ne contient pas la réponse : la question n'est pas suggérée, sans message d'échec.
    SANS_REPONSE = "sans_réponse"
    ECHEC = "échec"


class DossierQuestionAnswer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "dossier_question_answers"
    __table_args__ = (UniqueConstraint("dossier_id", "question", name="uq_dossier_question_answer"),)

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # Le rang de la question dans l'analyse : l'ordre dans lequel on les propose.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[QuestionAnswerStatus] = mapped_column(
        Enum(QuestionAnswerStatus, name="question_answer_status"), nullable=False, default=QuestionAnswerStatus.EN_COURS
    )
    # La réponse en markdown, avec ses citations ([1]).
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Les passages cités : {number, dossier_document_id, page_ids, excerpt}, comme `MessageSource`.
    sources: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Ce que la réponse a lu : vide tant qu'elle n'est pas finie (un échec est donc recalculé à la fois suivante).
    fingerprint: Mapped[str] = mapped_column(String, nullable=False, default="")
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
