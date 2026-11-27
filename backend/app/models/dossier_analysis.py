"""Analyse de dossier (issue #112, parent #106).

Document de travail d'un dossier, **une analyse par exécution** :

- ``DossierAnalysis`` : l'analyse d'une exécution (contexte, statut).
- ``AnalysisUnit`` : une unité de calcul (un appel au LLM ou une étape) et
  l'empreinte de ses entrées - sert à décider reprendre ou recalculer à la
  relance (#119). Une unité qui n'a produit aucun élément existe quand même.
- ``AnalysisElement`` : un élément de l'analyse (classification, entité,
  relation, synthèse, champ libre), lié à son unité.
- ``AnalysisElementVersion`` : valeurs successives d'un élément, en ajout
  seul (jamais modifiée) - la valeur d'un instructeur est stockée à côté de
  la prédiction du modèle, sans l'écraser.
- ``AnalysisRevision`` / ``AnalysisRevisionItem`` : instantané de l'analyse
  entière (une version retenue par élément), pour générer un document
  depuis « la version N » (#107), comparer ou restaurer.

Tout est interne : aucune exposition côté usager (#96).
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.document_page import BoundingBox
from app.models.encrypted import EncryptedString


class DossierAnalysisStatus(enum.StrEnum):
    BROUILLON = "brouillon"
    VALIDEE = "validée"
    FIGEE = "figée"


class AnalysisUnitKind(enum.StrEnum):
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    AGENT = "agent"


class AnalysisUnitStatus(enum.StrEnum):
    EN_COURS = "en_cours"
    TERMINE = "terminé"
    ECHEC = "échec"


class AnalysisElementKind(enum.StrEnum):
    CLASSIFICATION = "classification"
    ENTITY = "entity"
    RELATION = "relation"
    SYNTHESIS = "synthesis"
    FIELD = "field"


class ElementVersionOrigin(enum.StrEnum):
    # Produite par le modèle (lien vers la prédiction source).
    MODEL = "model"
    # Apportée ou restaurée par un instructeur.
    INSTRUCTOR = "instructor"
    # Reprise telle quelle d'une analyse précédente (relance incrémentale, #119).
    CARRIED_OVER = "carried_over"


class DossierAnalysis(UUIDMixin, TimestampMixin, Base):
    """Analyse d'une exécution d'un dossier. L'analyse *courante* d'un
    dossier est la plus récente (``sequence`` la plus élevée)."""

    __tablename__ = "dossier_analyses"
    __table_args__ = (UniqueConstraint("dossier_id", "sequence", name="uq_dossier_analyses_dossier_id_sequence"),)

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Numéro d'ordre de l'exécution dans le dossier (1, 2, ...).
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DossierAnalysisStatus] = mapped_column(
        Enum(DossierAnalysisStatus, name="dossier_analysis_status"),
        nullable=False,
        default=DossierAnalysisStatus.BROUILLON,
    )
    # Contexte de l'exécution (porté ici plutôt que répété sur chaque version
    # produite par le modèle).
    analyse_version: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Analyse dont celle-ci reprend des éléments (relance incrémentale, #119).
    previous_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossier_analyses.id", ondelete="SET NULL"), nullable=True
    )


class AnalysisUnit(UUIDMixin, TimestampMixin, Base):
    """Unité de calcul : une page (classification), un lot de pages d'un même
    document x un groupe de définitions (extraction) ou une étape d'agent.
    Enregistrée même sans résultat, pour ne pas la recalculer inutilement."""

    __tablename__ = "analysis_units"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossier_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[AnalysisUnitKind] = mapped_column(Enum(AnalysisUnitKind, name="analysis_unit_kind"), nullable=False)
    # Ce que couvre l'unité (page, document + plage de pages + groupe de
    # définitions, étape...) - forme libre, propre à chaque type d'unité.
    description: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[AnalysisUnitStatus] = mapped_column(
        Enum(AnalysisUnitStatus, name="analysis_unit_status"), nullable=False, default=AnalysisUnitStatus.EN_COURS
    )
    # Hash des entrées de l'unité (texte des pages lues, définitions, prompt,
    # modèle, version du pipeline) : calculé par #113, comparé par #119.
    input_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    element_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Unité d'origine quand celle-ci a été reprise d'une analyse précédente.
    source_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analysis_units.id", ondelete="SET NULL"), nullable=True
    )


class AnalysisElement(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "analysis_elements"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossier_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Vide pour un élément ajouté à la main.
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analysis_units.id", ondelete="SET NULL"), nullable=True, index=True
    )
    kind: Mapped[AnalysisElementKind] = mapped_column(
        Enum(AnalysisElementKind, name="analysis_element_kind"), nullable=False
    )
    # Colonnes descriptives, non uniques : ce qu'est l'élément. Le nom de la
    # définition est conservé même si la définition est ensuite supprimée.
    definition_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    definition_name: Mapped[str | None] = mapped_column(String, nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossier_documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    first_page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Une prédiction ne produit qu'un élément : rend la génération idempotente.
    source_prediction_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("document_predictions.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    # Élément d'origine quand celui-ci a été repris d'une analyse précédente.
    origin_element_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analysis_elements.id", ondelete="SET NULL"), nullable=True
    )
    # Pointeurs vers les versions (FK ajoutées après la création de
    # analysis_element_versions : dépendance circulaire). La version
    # *retenue* fait foi ; la dernière version *produite par le modèle* peut
    # en différer quand un instructeur a apporté sa valeur.
    retained_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "analysis_element_versions.id", ondelete="SET NULL", use_alter=True, name="fk_analysis_elements_retained"
        ),
        nullable=True,
    )
    latest_model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "analysis_element_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_analysis_elements_latest_model",
        ),
        nullable=True,
    )
    # « À revoir » : les entrées de l'élément ont changé alors qu'un
    # instructeur avait validé une valeur (#119). Effacé quand il confirme
    # ou corrige.
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Verrou court par élément (travail à plusieurs, #118) - réservé.
    locked_by: Mapped[str | None] = mapped_column(String, nullable=True)
    locked_by_name: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Lecture seule : toutes les versions de l'élément, de la plus ancienne à la
    # plus récente. primaryjoin explicite car l'élément pointe aussi vers deux
    # de ses versions (retenue, dernière du modèle).
    versions: Mapped[list["AnalysisElementVersion"]] = relationship(
        "AnalysisElementVersion",
        primaryjoin="AnalysisElement.id == AnalysisElementVersion.element_id",
        foreign_keys="AnalysisElementVersion.element_id",
        order_by="AnalysisElementVersion.version_number",
        viewonly=True,
    )


class AnalysisElementVersion(UUIDMixin, TimestampMixin, Base):
    """Version d'un élément. Jamais modifiée après coup : restaurer une
    version en ajoute une nouvelle."""

    __tablename__ = "analysis_element_versions"
    __table_args__ = (UniqueConstraint("element_id", "version_number", name="uq_analysis_element_versions_number"),)

    element_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analysis_elements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Forme selon le type d'élément (voir app.schemas.dossier_analysis).
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin: Mapped[ElementVersionOrigin] = mapped_column(
        Enum(ElementVersionOrigin, name="element_version_origin"), nullable=False
    )
    # origin == MODEL : prédiction source.
    prediction_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("document_predictions.id", ondelete="SET NULL"), nullable=True
    )
    # origin == INSTRUCTOR : auteur, motif et source de la modification
    # (message de chat, note, proposition...).
    author_id: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    # Version dont celle-ci est la restauration, ou version reprise
    # (CARRIED_OVER) d'une analyse précédente.
    restored_from_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analysis_element_versions.id", ondelete="SET NULL"), nullable=True
    )
    origin_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analysis_element_versions.id", ondelete="SET NULL"), nullable=True
    )
    # Issue #120 : ce que l'ancienne validation de prédiction (PredictionValidation)
    # exprimait. ``validation_status`` vaut « validé », « corrigé » ou « rejeté »
    # quand la version vient d'une validation de prédiction (route
    # .../predictions/{id}/validations ou migration de l'historique existant) ;
    # ``bounding_box_id`` est la zone corrigée, quand l'instructeur en a tracé une.
    validation_status: Mapped[str | None] = mapped_column(String, nullable=True)
    bounding_box_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("bounding_boxes.id", ondelete="SET NULL"), nullable=True
    )

    bounding_box: Mapped["BoundingBox | None"] = relationship("BoundingBox", foreign_keys=[bounding_box_id])


class AnalysisRevision(UUIDMixin, TimestampMixin, Base):
    """Instantané de l'analyse : une version retenue par élément."""

    __tablename__ = "analysis_revisions"
    __table_args__ = (UniqueConstraint("analysis_id", "number", name="uq_analysis_revisions_analysis_id_number"),)

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossier_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    author_id: Mapped[str | None] = mapped_column(String, nullable=True)


class AnalysisRevisionItem(Base):
    __tablename__ = "analysis_revision_items"
    __table_args__ = (PrimaryKeyConstraint("revision_id", "element_id"),)

    revision_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analysis_revisions.id", ondelete="CASCADE"), nullable=False
    )
    element_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analysis_elements.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analysis_element_versions.id", ondelete="CASCADE"), nullable=False
    )


class AnalysisPresence(Base):
    """Présence d'un instructeur sur une analyse (issue #118) : sur quel élément il
    est, et s'il le consulte ou l'édite. Éphémère : mise à jour par battement de
    cœur, ignorée passé ``PRESENCE_TTL_SECONDS`` (jamais une trace durable)."""

    __tablename__ = "analysis_presence"
    __table_args__ = (PrimaryKeyConstraint("analysis_id", "user_id"),)

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossier_analyses.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    # Élément concerné ; vide quand l'instructeur est sur l'analyse sans élément précis.
    element_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analysis_elements.id", ondelete="CASCADE"), nullable=True
    )
    mode: Mapped[str] = mapped_column(String, nullable=False, default="viewing")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
