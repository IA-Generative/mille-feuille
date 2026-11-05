"""Les modèles du hub LLM que l'application connaît, et ce que l'administrateur dit qu'ils savent faire.

Le **type** d'un modèle (complétion, embeddings, audio, image, vidéo) est lu par le backend sur le hub. Une
**capacité** est définie par l'administrateur : un nom et une description (« Tâches lourdes » : capable de raisonner
sur plusieurs documents ; « Outils » : capable de répondre en appelant des outils). Rien n'est déduit du modèle. Un
modèle est enregistré par son nom (celui du hub) avec ses capacités et son ordre de préférence : par défaut, le premier
modèle actif fait tout ; en mode auto, le modèle est choisi selon les capacités que la demande demande (voir
`app/agent/model_router.py`)."""

import enum

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

llm_model_capabilities = Table(
    "llm_model_capabilities",
    Base.metadata,
    Column("model_id", PG_UUID(as_uuid=True), ForeignKey("llm_models.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "capability_id", PG_UUID(as_uuid=True), ForeignKey("llm_capabilities.id", ondelete="CASCADE"), primary_key=True
    ),
)


class LlmModelType(enum.StrEnum):
    """Ce qu'un modèle sait faire techniquement. Le backend le lit sur le hub : l'administrateur ne le saisit pas."""

    COMPLETION = "completion"
    EMBEDDING = "embedding"
    AUDIO = "audio"
    IMAGE = "image"  # traite ou produit des images
    VIDEO = "video"


class LlmCapabilityConfig(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "llm_capabilities"

    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # Lue par le modèle qui classe les demandes en mode auto : ce que la capacité permet de faire.
    description: Mapped[str] = mapped_column(Text, nullable=False)


class LlmModelConfig(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "llm_models"

    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # Ordre de préférence : le premier modèle actif est celui de tout le monde hors mode auto.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Les LlmModelType que le hub a révélés (voir services/llm_hub.py) ; NULL : pas encore lus, on ne sait pas.
    types: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    capabilities: Mapped[list[LlmCapabilityConfig]] = relationship(
        secondary=llm_model_capabilities, order_by=LlmCapabilityConfig.name, lazy="selectin"
    )


class LlmRoutingSettings(Base):
    """Le réglage du choix du modèle : une seule ligne (`id` = 1)."""

    __tablename__ = "llm_routing_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    # Faux : le premier modèle actif fait tout. Vrai : le modèle suit les capacités que la demande demande.
    auto_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
