from pydantic import BaseModel

from app.schemas.analyse import Version
from app.services.search.settings import EffectiveSearchSettings, SearchSettings


class SearchSettingsOut(BaseModel):
    """Les réglages enregistrés par l'analyse, ce qu'ils donnent une fois les défauts de la plateforme appliqués (ou
    pourquoi ce n'est pas possible), et si on peut les modifier."""

    settings: SearchSettings
    effective: EffectiveSearchSettings | None = None
    fingerprint: str | None = None
    # Pourquoi les réglages ne se résolvent pas (par exemple : aucun modèle d'embeddings).
    problem: str | None = None
    # Vrai quand au moins un dossier de l'analyse est indexé : les réglages ne se modifient plus.
    locked: bool = False
    versions: list[Version[SearchSettings]] = []
