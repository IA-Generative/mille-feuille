"""Réglages de recherche d'une analyse : découpage des pages en passages et modèle d'embeddings.

Ils sont stockés sur l'analyse (versionnés) et **résolus** avant d'atteindre un worker : un champ resté vide prend la
valeur par défaut de la plateforme. L'empreinte résume ce qui change le contenu de l'index (stratégie, modèles et
paramètres de découpage) ; `window`, qui ne joue qu'à la recherche, n'en fait pas partie."""

import hashlib
import json
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.config import SearchSettings as PlatformSearchSettings

STRATEGY_AI = "ia"
STRATEGY_CLASSIC = "classique"

DEFAULT_SIZE = 1000
DEFAULT_OVERLAP = 150
DEFAULT_WINDOW = 1


class SearchSettings(BaseModel):
    """Ce que l'analyse enregistre. Un modèle laissé vide veut dire « celui de la plateforme »."""

    strategy: Literal["ia", "classique"] = STRATEGY_AI
    # Modèle qui découpe les pages (stratégie « ia »).
    chunk_model: str | None = Field(default=None, max_length=200)
    # Découpage classique : taille d'un passage et chevauchement, en caractères.
    size: int = Field(default=DEFAULT_SIZE, ge=100, le=10000)
    overlap: int = Field(default=DEFAULT_OVERLAP, ge=0)
    # Fenêtre glissante : nombre de passages voisins renvoyés de chaque côté d'un passage trouvé.
    window: int = Field(default=DEFAULT_WINDOW, ge=0, le=5)
    embedding_model: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _overlap_below_size(self) -> Self:
        if self.overlap >= self.size:
            raise ValueError("Le chevauchement doit être inférieur à la taille d'un passage")
        return self


class EffectiveSearchSettings(BaseModel):
    """Les réglages une fois les défauts de la plateforme appliqués : ce qu'un worker reçoit."""

    strategy: Literal["ia", "classique"]
    chunk_model: str | None
    size: int
    overlap: int
    window: int
    embedding_model: str

    @property
    def fingerprint(self) -> str:
        return fingerprint(self)


def resolve(stored: dict | None, platform: PlatformSearchSettings | None = None) -> EffectiveSearchSettings:
    """Réglages effectifs d'une analyse. Lève ValueError si un modèle manque et que la plateforme n'en fournit pas."""
    platform = platform or PlatformSearchSettings()
    settings = SearchSettings.model_validate(stored or {})
    embedding_model = settings.embedding_model or platform.SEARCH_EMBEDDING_MODEL
    if not embedding_model:
        raise ValueError(
            "Aucun modèle d'embeddings : choisissez-en un dans l'analyse ou configurez celui de la plateforme"
        )
    chunk_model = None
    if settings.strategy == STRATEGY_AI:
        chunk_model = settings.chunk_model or platform.SEARCH_CHUNK_MODEL
        if not chunk_model:
            raise ValueError(
                "Aucun modèle de découpage : choisissez-en un dans l'analyse ou configurez celui de la plateforme"
            )
    return EffectiveSearchSettings(
        strategy=settings.strategy,
        chunk_model=chunk_model,
        size=settings.size,
        overlap=settings.overlap,
        window=settings.window,
        embedding_model=embedding_model,
    )


def fingerprint(settings: EffectiveSearchSettings | dict) -> str:
    """Empreinte courte de ce qui détermine le contenu de l'index."""
    data = settings.model_dump() if isinstance(settings, EffectiveSearchSettings) else settings
    relevant = {
        "strategy": data["strategy"],
        "embedding_model": data["embedding_model"],
        # Selon la stratégie, seuls les paramètres qui jouent comptent : changer la taille ne réindexe pas un
        # découpage par IA, et changer le modèle de découpage ne réindexe pas un découpage classique.
        **(
            {"chunk_model": data["chunk_model"]}
            if data["strategy"] == STRATEGY_AI
            else {"size": data["size"], "overlap": data["overlap"]}
        ),
    }
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:12]
