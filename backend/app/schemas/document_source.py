import uuid

from pydantic import BaseModel, ConfigDict, field_validator


class DocumentSourceIn(BaseModel):
    name: str
    description: str = ""

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Le nom de la source ne peut pas être vide.")
        return value

    @field_validator("description")
    @classmethod
    def _strip_description(cls, value: str) -> str:
        return value.strip()


class DocumentSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    # Source du catalogue d'une analyse, ou source « tampon » d'un dossier « à ranger » (jamais les deux).
    analyse_id: uuid.UUID | None
    dossier_id: uuid.UUID | None


class DocumentSourceAssignIn(BaseModel):
    """Source d'un document déjà déposé ; `null` la retire."""

    source_id: uuid.UUID | None
