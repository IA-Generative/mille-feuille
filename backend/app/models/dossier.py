import enum
import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, DateTime, Enum, ForeignKey, Identity, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.dossier_access import Visibility
from app.models.summary import SummaryStatus
from app.services.due_date import DEFAULT_THRESHOLDS, DueInfo, closed_before_due, due_info, today_in_paris

if TYPE_CHECKING:
    from app.models.analyse import StatusDefinition
    from app.models.app_user import AppUser
    from app.models.conversation import Conversation
    from app.models.document_page import DocumentPage
    from app.models.document_source import DocumentSource
    from app.models.execution_log import ExecutionLog
    from app.models.summary import DocumentSummary, DossierSummary


class DossierStatus(enum.StrEnum):
    EN_ATTENTE = "en_attente"
    EN_COURS = "en_cours"
    TERMINE = "terminé"
    ARRETE = "arrêté"
    ECHEC = "échec"


class ExecutionStepKind(enum.StrEnum):
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    AGENT = "agent"


class ExecutionStepStatus(enum.StrEnum):
    EN_COURS = "en_cours"
    TERMINE = "terminé"
    ECHEC = "échec"


class TextExtractionStatus(enum.StrEnum):
    """État du run d'extraction de texte (worker document_process,
    app.tasks.extract_document_text) pour un document - pas un
    ExecutionStep : ça tourne dès l'upload, indépendamment d'un lancement de
    dossier, et alimente les pages/bbox qu'une classification/extraction
    lira ensuite."""

    EN_ATTENTE = "en_attente"
    EN_COURS = "en_cours"
    TERMINE = "terminé"
    ECHEC = "échec"


class SuggestionStatus(enum.StrEnum):
    """État de génération des suggestions d'analyse pour un dossier « à
    ranger » (issue #54). Le worker agent_execution génère les suggestions
    après les résumés (issue #52) et les dépose via l'API interne."""

    EN_ATTENTE = "en_attente"
    EN_COURS = "en_cours"
    TERMINE = "terminé"
    ECHEC = "échec"


class Dossier(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "dossiers"

    name: Mapped[str] = mapped_column(String, nullable=False)
    # Qui voit le dossier (issue #177). « analyse » est la valeur historique (et celle des créations
    # programmatiques : MCP, runs éphémères) ; l'API des utilisateurs crée des dossiers « restricted ».
    visibility: Mapped[str] = mapped_column(String, nullable=False, default=Visibility.ANALYSE.value)
    # Numéro d'ordre, strictement croissant, attribué par la base : il fait la référence lisible du dossier
    # (« DOS-2026-0042 », cf. `reference`), que les instructeurs se communiquent (issue #173).
    ref_number: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False, unique=True)
    # Un dossier « à ranger » (issue #54) n'a pas d'analyse assignée :
    # analyse_id est nullable, l'utilisateur choisira (ou validera la
    # suggestion de l'IA) après upload des documents et génération des
    # résumés. On garde ondelete="RESTRICT" quand non-NULL : impossible de
    # supprimer une analyse encore liée à un dossier.
    analyse_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # Snapshot au lancement de la version de l'analyse utilisée (voir
    # AnalyseRepository.get_version : dérivée du nombre de FieldVersion).
    analyse_version: Mapped[str] = mapped_column(String, nullable=False, default="v1")
    status: Mapped[DossierStatus] = mapped_column(
        Enum(DossierStatus, name="dossier_status"), nullable=False, default=DossierStatus.EN_ATTENTE
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Statut de dossier défini par son analyse (issue #168) : distinct de
    # `status` ci-dessus, qui est l'état d'exécution de l'analyse automatique.
    # NULL pour un dossier « à ranger » (pas d'analyse, donc pas de statuts) ;
    # RESTRICT : un statut encore utilisé ne se supprime pas sans remplaçant.
    workflow_status_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("status_definitions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # Date de clôture : posée quand le dossier passe dans un statut final,
    # effacée s'il est rouvert. Alimente les indicateurs du tableau de bord (#174).
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Date d'échéance (issue #172) : un jour du calendrier, pas un instant. NULL = pas d'échéance.
    due_at: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    # Valeurs des colonnes personnalisées du suivi (issue #173) : {identifiant du champ: valeur}. Les définitions sont
    # sur l'analyse ; la valeur d'un champ supprimé reste ici, récupérable si le champ revient.
    custom_values: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Personne responsable du dossier (issue #173) : une seule ; NULL = non affecté. Doit figurer dans
    # l'annuaire local (app_users) ; SET NULL si la ligne disparaît, l'historique garde le nom.
    assignee_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("app_users.user_id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # État de génération du résumé global du dossier (issue #52).
    summary_status: Mapped[SummaryStatus] = mapped_column(
        Enum(SummaryStatus, name="summary_status"),
        nullable=False,
        default=SummaryStatus.EN_ATTENTE,
    )
    summary_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Suggestions d'analyse pour un dossier « à ranger » (issue #54) :
    # liste de {analyse_id, name, score, rationale} générée par le LLM à
    # partir des résumés du dossier et des analyses disponibles. Conservé
    # même après rattachement (historique).
    suggested_analyses: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    suggestion_status: Mapped[SuggestionStatus] = mapped_column(
        Enum(SuggestionStatus, name="suggestion_status"),
        nullable=False,
        default=SuggestionStatus.EN_ATTENTE,
    )

    workflow_status: Mapped["StatusDefinition | None"] = relationship(lazy="selectin")
    assignee: Mapped["AppUser | None"] = relationship(lazy="selectin")
    execution_steps: Mapped[list["ExecutionStep"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan", order_by="ExecutionStep.started_at"
    )
    documents: Mapped[list["DossierDocument"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan", order_by="DossierDocument.created_at"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan", order_by="Conversation.created_at"
    )
    summaries: Mapped[list["DossierSummary"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan", order_by="DossierSummary.created_at.desc()"
    )

    @property
    def reference(self) -> str:
        """Référence lisible : année de création et numéro d'ordre sur 4 chiffres au moins."""
        return f"DOS-{self.created_at.astimezone(UTC).year}-{self.ref_number:04d}"

    @property
    def due(self) -> DueInfo | None:
        """Niveau d'échéance (loin, proche, dépassée, clos) selon les seuils de l'analyse (issue #172)."""
        thresholds = self.__dict__.get("analyse_due_thresholds") or DEFAULT_THRESHOLDS
        return due_info(self.due_at, thresholds, today_in_paris(), closed=self.closed_at is not None)

    @property
    def closed_before_due(self) -> bool | None:
        """Clos au plus tard le jour de l'échéance ? ``None`` si la question ne se pose pas."""
        return closed_before_due(self.closed_at, self.due_at)

    @property
    def summary(self) -> "DossierSummary | None":
        """Dernier résumé généré (le plus récent par created_at), ou None."""
        return self.summaries[0] if self.summaries else None


class ExecutionStep(UUIDMixin, Base):
    __tablename__ = "execution_steps"

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[ExecutionStepKind] = mapped_column(Enum(ExecutionStepKind, name="execution_step_kind"), nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[ExecutionStepStatus] = mapped_column(
        Enum(ExecutionStepStatus, name="execution_step_status"), nullable=False, default=ExecutionStepStatus.EN_COURS
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Résultat produit par l'étape, présenté dans la page de résultat. Absent
    # tant que l'étape n'est pas terminée, ou pour un agent dont la sortie
    # n'est pas activée (Agent.output == False).
    output: Mapped[str | None] = mapped_column(Text, nullable=True)

    dossier: Mapped["Dossier"] = relationship(back_populates="execution_steps")
    logs: Mapped[list["ExecutionLog"]] = relationship(
        back_populates="execution_step", cascade="all, delete-orphan", order_by="ExecutionLog.created_at"
    )


class DossierDocument(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "dossier_documents"

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Clé de l'objet dans le bucket S3 (le contenu du fichier n'est jamais
    # stocké en base) et type MIME déclaré à l'upload.
    s3_key: Mapped[str] = mapped_column(String, nullable=False)
    mimetype: Mapped[str] = mapped_column(String, nullable=False)
    # Nature du document (ex: "CNI", "avis d'imposition") : posée par la
    # classification documentaire de l'analyse, ou corrigée manuellement.
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    text_extraction_status: Mapped[TextExtractionStatus] = mapped_column(
        Enum(TextExtractionStatus, name="text_extraction_status"),
        nullable=False,
        default=TextExtractionStatus.EN_ATTENTE,
    )
    text_extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Empreinte SHA-256 du contenu du fichier, calculée par le worker
    # document_process au moment de l'extraction (les bytes sont déjà en
    # mémoire). Permet de détecter les doublons et les fichiers identiques
    # re-uploadés.
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # État de génération du résumé du document (issue #52).
    summary_status: Mapped[SummaryStatus] = mapped_column(
        Enum(SummaryStatus, name="summary_status"),
        nullable=False,
        default=SummaryStatus.EN_ATTENTE,
    )
    summary_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # D'où vient le fichier (courrier, guichet…) ; NULL s'il n'a pas de source, ou si elle a été supprimée.
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("document_sources.id", ondelete="SET NULL"), nullable=True, index=True
    )

    dossier: Mapped["Dossier"] = relationship(back_populates="documents")
    # selectin : la source est sérialisée avec chaque document, quel que soit le chemin qui le charge.
    source: Mapped["DocumentSource | None"] = relationship(lazy="selectin")
    pages: Mapped[list["DocumentPage"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentPage.page_number"
    )
    summaries: Mapped[list["DocumentSummary"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentSummary.created_at.desc()"
    )

    @property
    def summary(self) -> "DocumentSummary | None":
        """Dernier résumé généré (le plus récent par created_at), ou None."""
        return self.summaries[0] if self.summaries else None
