import uuid

from pydantic import BaseModel, Field


class DossierSearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    limit: int = Field(default=20, ge=1, le=50)


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


class DossierSearchOut(BaseModel):
    """Les dossiers les plus pertinents ; `total` compte tous ceux trouvés. Les mots cherchés ne sont pas répétés."""

    dossiers: list[FoundDossierOut]
    total: int
