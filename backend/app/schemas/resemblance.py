import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.dossier_search import FoundDossierOut, LinkOccurrenceOut

Scope = Literal["all", "within", "across"]
Certainty = Literal["identical", "probable", "to_check"]


class CriterionIn(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    origin: Literal["analysis", "file"]
    name: str = Field(min_length=1, max_length=200)
    # Entités tenues pour équivalentes (acceptées par l'administrateur) ; aucune pour « même fichier ».
    entity_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    refused_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def _entities_match_the_origin(self) -> "CriterionIn":
        if self.origin == "analysis" and not self.entity_ids:
            raise ValueError("Un critère d'entité cite au moins une entité.")
        if self.origin == "file" and (self.entity_ids or self.refused_ids):
            raise ValueError("« Même fichier » ne cite aucune entité.")
        return self


class ThemeIn(BaseModel):
    name: str = Field(max_length=120)
    description: str = Field(default="", max_length=2000)
    scope: Scope = "all"
    certainty: Certainty = "to_check"
    active: bool = True
    criteria: list[CriterionIn] = Field(min_length=1, max_length=5)

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Le nom du thème est obligatoire.")
        return value.strip()


class ThemeVersionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    content: ThemeIn


class ThemeOut(ThemeIn):
    id: uuid.UUID
    computed_at: datetime | None
    # Dossiers visibles de la personne répartis en groupes (au moins deux par groupe).
    group_count: int = 0
    # Pour les administrateurs : l'historique, et les entités citées qu'aucune analyse ne définit plus.
    versions: list[ThemeVersionOut] = []
    missing_entity_ids: list[uuid.UUID] = []


class ThemeListOut(BaseModel):
    # Faux : le calcul est désactivé sur cet environnement, aucun groupe n'est produit.
    enabled: bool
    items: list[ThemeOut]


class GroupOut(BaseModel):
    key: str
    label: str
    reason: str
    certainty: Certainty
    dossiers: list[FoundDossierOut]
    occurrences: list[LinkOccurrenceOut]
    dismissed: bool = False


class GroupPageOut(BaseModel):
    items: list[GroupOut]
    total: int
    page: int
    page_size: int


class EntityOut(BaseModel):
    id: uuid.UUID
    name: str
    definition: str
    type: str
    analyse_name: str


class SuggestionsIn(BaseModel):
    """Les entités proches de celles-ci, ou d'une description."""

    entity_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    text: str = Field(default="", max_length=500)


class SuggestionsOut(BaseModel):
    # Faux : pas de base vectorielle ou de modèle d'embeddings, on choisit les entités à la main.
    available: bool
    items: list[EntityOut]
