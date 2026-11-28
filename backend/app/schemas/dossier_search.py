import uuid
from typing import Literal

from pydantic import BaseModel, Field


class DossierSearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    limit: int = Field(default=20, ge=1, le=50)
    # Sans détails : seulement les dossiers, sans extraits ni points communs (choisir un dossier par son nom).
    details: bool = True


class DossierLinksIn(BaseModel):
    dossier_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)
    # Ajoute les autres dossiers visibles liés à au moins un des dossiers de départ.
    include_related: bool = True


class SearchSegmentOut(BaseModel):
    text: str
    highlighted: bool


class SearchExcerptOut(BaseModel):
    """Où les mots ont été trouvés : le texte d'une page, une valeur extraite (`field`) ou le nom d'un document."""

    document_id: uuid.UUID | None = None
    document_name: str | None = None
    page: int | None = None
    # Nom de l'entité, du champ ou de la classification, pour une valeur extraite.
    field: str | None = None
    segments: list[SearchSegmentOut]


class FoundDossierOut(BaseModel):
    id: uuid.UUID
    reference: str
    name: str
    analyse_name: str | None
    theme_name: str | None
    excerpts: list[SearchExcerptOut]


class LinkOccurrenceOut(BaseModel):
    """La preuve d'un lien : où le point commun apparaît dans un dossier."""

    dossier_id: uuid.UUID
    document_id: uuid.UUID | None = None
    document_name: str | None = None
    page: int | None = None
    # La valeur telle qu'elle est écrite dans ce dossier ; vide pour un document identique.
    text: str = ""
    # « Analyse X · nom de l'entité » ; absent pour un document identique.
    origin: str | None = None


class SharedItemOut(BaseModel):
    """Un point commun à au moins deux des dossiers montrés."""

    id: str
    kind: Literal["identifier", "value", "document"]
    # Écritures différentes rapprochées (#648) : un rapprochement à vérifier, jamais une identité.
    uncertain: bool = False
    label: str
    dossier_ids: list[uuid.UUID]
    occurrences: list[LinkOccurrenceOut]


class HiddenLinksOut(BaseModel):
    """Des dossiers non accessibles liés aux résultats : un nombre par thème, rien qui les désigne (#647)."""

    theme_name: str | None
    count: int
    # Les dossiers **accessibles** auxquels ils sont liés.
    dossier_ids: list[uuid.UUID]


class DossierSearchOut(BaseModel):
    """Les dossiers les plus pertinents ; `total` compte tous ceux trouvés. Les mots cherchés ne sont pas répétés."""

    dossiers: list[FoundDossierOut]
    total: int
    items: list[SharedItemOut] = []
    hidden: list[HiddenLinksOut] = []


class DossierLinksOut(BaseModel):
    """Les dossiers de départ d'abord (`anchor_ids`), puis les dossiers liés ; chaque point commun touche un départ."""

    anchor_ids: list[uuid.UUID]
    dossiers: list[FoundDossierOut]
    items: list[SharedItemOut]
    hidden: list[HiddenLinksOut] = []
