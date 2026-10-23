from pydantic import BaseModel

from app.schemas.analyse import Version
from app.schemas.search_index import AnalyseIndexOverview
from app.services.search.settings import EffectiveSearchSettings, SearchSettings


class SearchSettingsOut(BaseModel):
    """Les réglages enregistrés par l'analyse, ce qu'ils donnent une fois les défauts de la plateforme appliqués (ou
    pourquoi ce n'est pas possible), et l'état des index des dossiers."""

    settings: SearchSettings
    effective: EffectiveSearchSettings | None = None
    fingerprint: str | None = None
    # Pourquoi les réglages ne se résolvent pas (par exemple : aucun modèle d'embeddings).
    problem: str | None = None
    # Les index des dossiers de l'analyse par rapport à ces réglages.
    overview: AnalyseIndexOverview | None = None
    versions: list[Version[SearchSettings]] = []


class SearchSettingsPreviewOut(BaseModel):
    """Ce qu'un changement de réglages produirait, avant de l'enregistrer."""

    effective: EffectiveSearchSettings | None = None
    problem: str | None = None
    fingerprint: str | None = None
    # L'index change-t-il ? Non si seuls des réglages sans effet sur le contenu (la fenêtre) bougent.
    changes_index: bool
    # Dossiers indexés qui deviendraient obsolètes, sur l'ensemble des dossiers indexés.
    obsolete_dossiers: int
    indexed_dossiers: int
    # Un nouveau découpage par IA rappelle le modèle pour chaque page : le coût est plus élevé.
    uses_ai_chunking: bool
