import uuid

from pydantic import BaseModel, Field, field_validator

from app.schemas.analyse import Version


class AnalyseThemeIn(BaseModel):
    name: str = Field(max_length=120)
    description: str = Field(default="", max_length=2000)

    @field_validator("name", "description")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("Le nom du thème est obligatoire.")
        return value


class AnalyseThemeOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    # Analyses rangées dans ce thème (qui correspondent à la recherche, s'il y en a une).
    analyse_count: int
    name_versions: list[Version[str]] = []
    description_versions: list[Version[str]] = []


class AnalyseThemeList(BaseModel):
    items: list[AnalyseThemeOut]
    unthemed_count: int


class AnalyseThemeAssignment(BaseModel):
    theme_id: uuid.UUID | None = None


class AnalyseThemeRef(BaseModel):
    """Le thème qu'avait une analyse : le nom est gardé pour rester lisible si le thème est supprimé depuis."""

    theme_id: uuid.UUID | None = None
    name: str | None = None
