import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.services.due_date import DEFAULT_THRESHOLDS

if TYPE_CHECKING:
    from app.models.analyse_share import AnalyseShare


class EntityType(enum.StrEnum):
    TEXTE = "texte"
    DATE = "date"
    NOMBRE = "nombre"
    BOOLEEN = "booléen"
    IDENTIFIANT = "identifiant"


class AgentTool(enum.StrEnum):
    LECTURE_DOCUMENT = "lecture_document"
    RECHERCHE_WEB = "recherche_web"
    BASE_CONNAISSANCES = "base_connaissances"
    APPEL_AGENT = "appel_agent"
    CALCULATRICE = "calculatrice"
    VERIFICATION_COHERENCE = "verification_coherence"


class VersionedField(enum.StrEnum):
    """What a FieldVersion snapshot is a previous value of. classification_*
    and extraction_* rows key off analyse_id alone (agent_id NULL); agent_*
    rows also carry the owning agent_id."""

    CLASSIFICATION_PROMPT = "classification_prompt"
    CLASSIFICATION_LABELS = "classification_labels"
    EXTRACTION_PROMPT = "extraction_prompt"
    EXTRACTION_ENTITIES = "extraction_entities"
    AGENT_PROMPT = "agent_prompt"
    AGENT_TOOLS = "agent_tools"
    AGENT_OUTPUT = "agent_output"
    AGENT_MODEL = "agent_model"
    # Statuts de dossier de l'analyse (issue #168) : liste ordonnée avec identifiants
    # stables (un dossier y fait référence), restaurée à l'identique.
    STATUSES = "statuses"
    # Échéance des dossiers de l'analyse (issue #172) : durée par défaut et seuils de couleur.
    DUE_SETTINGS = "due_settings"
    CUSTOM_FIELDS = "custom_fields"
    # Collections de la base de connaissances que l'analyse autorise (issue #358) : liste de
    # {source_id, collection_id, name}, restaurée à l'identique.
    KNOWLEDGE_COLLECTIONS = "knowledge_collections"
    # Recherche dans les dossiers de l'analyse : découpage des pages en passages et modèle d'embeddings.
    SEARCH_SETTINGS = "search_settings"
    # Lecture des documents scannés : modèle du hub qui décrit les images et les tableaux (absent : celui de la
    # plateforme).
    OCR_SETTINGS = "ocr_settings"


class Analyse(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "analyses"

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Classification et extraction sont des analyses simples (un prompt
    # appliqué systématiquement, pas un agent) : un seul jeu de labels/
    # entités par analyse, embarqué directement plutôt qu'en table à part -
    # il n'y a jamais qu'une seule classification/extraction par analyse.
    # Échéance des dossiers (issue #172) : durée par défaut en jours depuis la création (NULL = pas d'échéance
    # automatique) et seuils de couleur {far_color, steps: [{days, color}], overdue_color}.
    default_due_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_thresholds: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: dict(DEFAULT_THRESHOLDS))

    # Colonnes personnalisées du suivi (issue #173) : liste de définitions {id, name, definition, type, required,
    # default_value, choices, currency}, versionnée (`VersionedField.CUSTOM_FIELDS`). Les valeurs sont sur le dossier.
    custom_fields: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    # Collections de la base de connaissances que le chat et les agents de l'analyse peuvent interroger, versionnées
    # (`VersionedField.KNOWLEDGE_COLLECTIONS`) : {source_id, collection_id, name}. Les droits restent ceux de la
    # personne.
    knowledge_collections: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)

    # Réglages de la recherche dans les dossiers (stratégie et paramètres de découpage, modèles), versionnés
    # (`VersionedField.SEARCH_SETTINGS`). Un champ absent prend la valeur par défaut de la plateforme.
    search_settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Réglages de la lecture des documents scannés (modèle qui décrit les images), versionnés
    # (`VersionedField.OCR_SETTINGS`). Le worker document_process les lit à l'extraction ; absents, ceux de la
    # plateforme.
    ocr_settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    classification_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Classification multi-label : plusieurs labels possibles par page (sinon un seul). Fixé à la création
    # (API éphémère) ; pas encore éditable via l'API standard, donc pas d'historique de versions.
    multi_label: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    extraction_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")

    labels: Mapped[list["LabelDefinition"]] = relationship(
        back_populates="analyse", cascade="all, delete-orphan", order_by="LabelDefinition.created_at"
    )
    entities: Mapped[list["EntityDefinition"]] = relationship(
        back_populates="analyse", cascade="all, delete-orphan", order_by="EntityDefinition.created_at"
    )
    statuses: Mapped[list["StatusDefinition"]] = relationship(
        back_populates="analyse", cascade="all, delete-orphan", order_by="StatusDefinition.position"
    )
    agents: Mapped[list["Agent"]] = relationship(
        back_populates="analyse", cascade="all, delete-orphan", order_by="Agent.created_at"
    )
    field_versions: Mapped[list["FieldVersion"]] = relationship(
        back_populates="analyse", cascade="all, delete-orphan", order_by="FieldVersion.created_at.desc()"
    )
    shares: Mapped[list["AnalyseShare"]] = relationship(
        back_populates="analyse", cascade="all, delete-orphan", order_by="AnalyseShare.created_at.desc()"
    )


class LabelDefinition(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "label_definitions"

    analyse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False, default="")

    analyse: Mapped["Analyse"] = relationship(back_populates="labels")


class EntityDefinition(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "entity_definitions"

    analyse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False, default="")
    type: Mapped[EntityType] = mapped_column(Enum(EntityType, name="entity_type"), nullable=False)

    analyse: Mapped["Analyse"] = relationship(back_populates="entities")


class StatusDefinition(UUIDMixin, TimestampMixin, Base):
    """Un statut de dossier défini par l'analyse (issue #168) : chaque analyse
    a son propre jeu de statuts, ordonné. Un statut est « initial » (celui que
    reçoit un dossier créé, un seul par analyse) et/ou « final » (le dossier est
    alors clos : voir Dossier.closed_at).

    À la différence des labels et des entités, un statut garde son identifiant
    quand on modifie la liste : les dossiers y font référence (Dossier.workflow_status_id)."""

    __tablename__ = "status_definitions"

    analyse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Couleur d'affichage, au format #RRGGBB.
    color: Mapped[str] = mapped_column(String, nullable=False, default="#6a6af4")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_initial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    analyse: Mapped["Analyse"] = relationship(back_populates="statuses")


class Agent(UUIDMixin, TimestampMixin, Base):
    """Un agent est créé librement par l'utilisateur pour un but métier
    propre à l'analyse (cohérence, rédaction, timeline...) : nom, prompt et
    outils, sans capacité prédéfinie - à la différence de la classification
    et de l'extraction qui sont des analyses systématiques."""

    __tablename__ = "agents"

    analyse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Si vrai, le résultat de cet agent est présenté comme une sortie visible
    # dans la page de résultat du dossier.
    output: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Identifiant de modèle tel que renvoyé par GET /models (id du hub LLM
    # configuré) ; NULL = pas de préférence, le hub par défaut sera utilisé.
    model: Mapped[str | None] = mapped_column(String, nullable=True)

    analyse: Mapped["Analyse"] = relationship(back_populates="agents")
    field_versions: Mapped[list["FieldVersion"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan", order_by="FieldVersion.created_at.desc()"
    )


class FieldVersion(UUIDMixin, TimestampMixin, Base):
    """A snapshot of a field's *previous* value, taken right before it was
    overwritten - the same versioning treatment applies to every editable
    field of an Analyse/Agent (prompt, labels, entities, tools, output),
    not just the prompt."""

    __tablename__ = "field_versions"

    analyse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL for classification_*/extraction_* fields (owned directly by the analyse).
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    field: Mapped[VersionedField] = mapped_column(Enum(VersionedField, name="versioned_field"), nullable=False)
    # Shape depends on `field`: a string for *_prompt, a bool for
    # agent_output, a JSON array of {name, definition[, type]} for
    # *_labels/*_entities, a JSON array of strings for agent_tools.
    content: Mapped[dict | list | str | bool] = mapped_column(JSONB, nullable=False)

    analyse: Mapped["Analyse"] = relationship(back_populates="field_versions")
    agent: Mapped["Agent | None"] = relationship(back_populates="field_versions")


# Seuils d'échéance de l'analyse du dossier (issue #172), lus avec le dossier lui-même : une sous-requête
# plutôt qu'une relation, pour ne pas charger (ni périmer) l'objet Analyse et ses listes.
from sqlalchemy import select as _select  # noqa: E402
from sqlalchemy.orm import column_property as _column_property  # noqa: E402

from app.models.dossier import Dossier as _Dossier  # noqa: E402

_Dossier.analyse_due_thresholds = _column_property(
    _select(Analyse.due_thresholds).where(Analyse.id == _Dossier.analyse_id).correlate_except(Analyse).scalar_subquery()
)
