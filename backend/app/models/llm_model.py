"""Les modèles du hub LLM que l'application connaît, avec ce qu'ils savent faire.

Un modèle est enregistré par son nom (celui du hub, tel que renvoyé par `GET /models`), avec ses **capacités**
(complétion de texte, embeddings, audio, vision, vidéo) et son **niveau** : 1 pour un modèle léger, 3 pour le plus
puissant. Par défaut, le premier modèle de complétion (le plus petit `position`) fait tout ; en mode auto
(`LLM_AUTO_MODE`), le modèle est choisi selon la difficulté de la demande (voir `app/agent/model_router.py`)."""

import enum

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class LlmCapability(enum.StrEnum):
    COMPLETION = "completion"
    EMBEDDING = "embedding"
    AUDIO = "audio"
    VISION = "vision"
    VIDEO = "video"


MIN_LEVEL, MAX_LEVEL = 1, 3


class LlmModelConfig(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "llm_models"

    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # Liste de LlmCapability (en texte : en ajouter une ne demande pas de migration).
    capabilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # 1 (léger) à 3 (puissant) : la difficulté la plus haute que le modèle prend en charge en mode auto.
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=MIN_LEVEL)
    # Ordre de préférence : le premier modèle de complétion actif est celui de tout le monde hors mode auto.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
