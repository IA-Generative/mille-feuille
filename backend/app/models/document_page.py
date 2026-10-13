import enum
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Enum, Float, ForeignKey, Integer, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.analyse import EntityDefinition, LabelDefinition
    from app.models.dossier import DossierDocument
    from app.models.dossier_analysis import AnalysisElement


class PredictionKind(enum.StrEnum):
    LABEL = "label"
    ENTITY = "entity"


class PredictionSource(enum.StrEnum):
    """D'où vient une prédiction de classification : le texte de la page (OCR + description VLM + LLM) ou son
    apparence (CLIP sur la capture). Les deux tournent sur chaque page ; les entités sont toujours textuelles."""

    TEXTUAL = "textual"
    VISUAL = "visual"


class PredictionValidationStatus(enum.StrEnum):
    VALIDATED = "validé"
    CORRECTED = "corrigé"
    REJECTED = "rejeté"


# Une prédiction peut couvrir plusieurs pages/zones : une classification
# n'en a qu'une (le "simplement liée à une page" reste vrai en pratique),
# mais une entité extraite peut s'étendre sur plusieurs pages, ou n'être
# précisément localisée que par un ensemble de bbox. Tables d'association
# pures (pas de classe mappée dédiée) : la relation n'a pas d'attribut
# propre, juste les deux FK.
prediction_pages = Table(
    "prediction_pages",
    Base.metadata,
    Column(
        "prediction_id",
        PG_UUID(as_uuid=True),
        ForeignKey("document_predictions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "document_page_id", PG_UUID(as_uuid=True), ForeignKey("document_pages.id", ondelete="CASCADE"), primary_key=True
    ),
)

prediction_bounding_boxes = Table(
    "prediction_bounding_boxes",
    Base.metadata,
    Column(
        "prediction_id",
        PG_UUID(as_uuid=True),
        ForeignKey("document_predictions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "bounding_box_id", PG_UUID(as_uuid=True), ForeignKey("bounding_boxes.id", ondelete="CASCADE"), primary_key=True
    ),
)


class DocumentPage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "document_pages"

    dossier_document_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossier_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Contenu textuel de la page (OCR / extraction de texte).
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Clé S3 d'une capture de la page (rendue par le worker) - jamais une
    # URL S3 signée exposée telle quelle : le frontend passe toujours par
    # GET /api/dossiers/.../pages/{id}/screenshot, qui la relaie.
    screenshot_key: Mapped[str | None] = mapped_column(String, nullable=True)

    @property
    def has_screenshot(self) -> bool:
        return self.screenshot_key is not None

    document: Mapped["DossierDocument"] = relationship(back_populates="pages")
    # Toutes les prédictions qui couvrent cette page (voir prediction_pages
    # ci-dessus) : pas de cascade delete-orphan ici, une prédiction peut
    # appartenir à plusieurs pages donc "orpheline" n'a pas de sens univoque.
    predictions: Mapped[list["DocumentPrediction"]] = relationship(
        secondary=prediction_pages, back_populates="pages", order_by="DocumentPrediction.created_at"
    )
    # Une page peut porter plusieurs zones (une par prédiction, potentiellement
    # d'autres plus tard) : la bbox est donc sa propre table rattachée à la
    # page plutôt que des colonnes plates dupliquées sur chaque table qui en
    # a besoin (prédiction, validation...).
    bounding_boxes: Mapped[list["BoundingBox"]] = relationship(
        back_populates="page", cascade="all, delete-orphan", order_by="BoundingBox.created_at"
    )


class BoundingBox(UUIDMixin, TimestampMixin, Base):
    """Zone normalisée (0-1, origine en haut à gauche) sur une page. Toujours
    rattachée à une DocumentPage ; une prédiction ou une validation qui en a
    une la référence par un ensemble (prediction_bounding_boxes) plutôt que
    d'en porter les coordonnées elle-même."""

    __tablename__ = "bounding_boxes"

    document_page_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    x_min: Mapped[float] = mapped_column(Float, nullable=False)
    y_min: Mapped[float] = mapped_column(Float, nullable=False)
    x_max: Mapped[float] = mapped_column(Float, nullable=False)
    y_max: Mapped[float] = mapped_column(Float, nullable=False)

    page: Mapped["DocumentPage"] = relationship(back_populates="bounding_boxes")


class DocumentPrediction(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "document_predictions"

    kind: Mapped[PredictionKind] = mapped_column(Enum(PredictionKind, name="prediction_kind"), nullable=False)
    # Nom du label/de l'entité prédite (ex: "CNI", "nom") - texte libre
    # plutôt qu'uniquement une FK vers LabelDefinition/EntityDefinition : la
    # prédiction doit survivre même si la définition est ensuite modifiée ou
    # supprimée (SET NULL). Quand la définition existe encore, le lien ci-
    # dessous permet de remonter à sa description/son type.
    name: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[PredictionSource] = mapped_column(
        Enum(PredictionSource, name="prediction_source"),
        nullable=False,
        default=PredictionSource.TEXTUAL,
        server_default=PredictionSource.TEXTUAL.name,
    )
    # kind == LABEL :
    label_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("label_definitions.id", ondelete="SET NULL"), nullable=True
    )
    # kind == ENTITY :
    entity_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entity_definitions.id", ondelete="SET NULL"), nullable=True
    )

    label_definition: Mapped["LabelDefinition | None"] = relationship()
    entity_definition: Mapped["EntityDefinition | None"] = relationship()
    # Une classification n'aura jamais qu'une page/bbox (l'ensemble fait
    # simplement un seul élément) ; une entité peut s'étendre sur plusieurs
    # pages ou n'être localisée que par plusieurs zones.
    pages: Mapped[list["DocumentPage"]] = relationship(
        secondary=prediction_pages, back_populates="predictions", order_by="DocumentPage.page_number"
    )
    bounding_boxes: Mapped[list["BoundingBox"]] = relationship(
        secondary=prediction_bounding_boxes, order_by="BoundingBox.created_at"
    )
    # Éléments de l'analyse de dossier produits par cette prédiction (#112) :
    # leurs versions portent l'historique de validation humaine (#120).
    analysis_elements: Mapped[list["AnalysisElement"]] = relationship("AnalysisElement", viewonly=True)

    @property
    def validations(self) -> list["PredictionValidationView"]:
        """Historique de validation humaine de la prédiction, au format de
        l'ancienne table ``prediction_validations`` (issue #120) : calculé à
        partir des versions d'instructeur des éléments d'analyse. Les
        chargements (selectinload) doivent inclure analysis_elements ->
        versions -> bounding_box."""
        views = [
            PredictionValidationView.from_version(self.id, element, version)
            for element in self.analysis_elements
            for version in element.versions
            if version.validation_status
        ]
        return sorted(views, key=lambda view: (view.created_at, view.version_number))


class PredictionValidation(UUIDMixin, TimestampMixin, Base):
    """Historique de validation humaine d'une prédiction : chaque ligne est un
    événement (validation, correction ou rejet), jamais modifiée après coup -
    la dernière ligne fait foi, comme le versioning de FieldVersion. Une
    correction de zone crée sa propre BoundingBox (jamais de mutation de
    celle de la prédiction d'origine) pour garder l'historique intact."""

    __tablename__ = "prediction_validations"

    prediction_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("document_predictions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bounding_box_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("bounding_boxes.id", ondelete="SET NULL"), nullable=True
    )
    validator_user_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[PredictionValidationStatus] = mapped_column(
        Enum(PredictionValidationStatus, name="prediction_validation_status"), nullable=False
    )
    corrected_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    bounding_box: Mapped["BoundingBox | None"] = relationship(foreign_keys=[bounding_box_id])


@dataclass
class PredictionValidationView:
    """Une validation de prédiction vue à travers une version d'élément
    d'analyse : mêmes champs que PredictionValidation (le contrat de l'API ne
    change pas)."""

    id: uuid.UUID
    prediction_id: uuid.UUID
    validator_user_id: str
    status: PredictionValidationStatus
    corrected_value: str | None
    bounding_box: "BoundingBox | None"
    created_at: datetime
    version_number: int

    @classmethod
    def from_version(cls, prediction_id: uuid.UUID, element: "AnalysisElement", version) -> "PredictionValidationView":
        status = PredictionValidationStatus(version.validation_status)
        corrected = None
        if status == PredictionValidationStatus.CORRECTED:
            # Valeur texte : « label » d'une classification, « value » d'une entité.
            corrected = str(version.value.get("label", version.value.get("value", "")))
        return cls(
            id=version.id,
            prediction_id=prediction_id,
            validator_user_id=version.author_id or "",
            status=status,
            corrected_value=corrected,
            bounding_box=version.bounding_box,
            created_at=version.created_at,
            version_number=version.version_number,
        )
