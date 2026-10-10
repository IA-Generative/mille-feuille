import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.analyse import AgentTool, EntityType
from app.models.analyse_share import AnalyseShareKind
from app.services.custom_fields import MAX_FIELDS_PER_ANALYSE, validate_value


class Version[T](BaseModel):
    id: uuid.UUID
    content: T
    created_at: datetime


class LabelDefinitionIn(BaseModel):
    name: str
    definition: str = ""


class LabelDefinitionOut(LabelDefinitionIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


class EntityDefinitionIn(BaseModel):
    name: str
    definition: str = ""
    type: EntityType


class EntityDefinitionOut(EntityDefinitionIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


# Couleur d'un statut : #RRGGBB.
HEX_COLOR_PATTERN = r"^#[0-9a-fA-F]{6}$"


class StatusDefinitionIn(BaseModel):
    # Absent pour un nouveau statut ; fourni pour conserver l'identité d'un statut existant
    # (les dossiers y font référence).
    id: uuid.UUID | None = None
    name: str
    color: str = Field(default="#6a6af4", pattern=HEX_COLOR_PATTERN)
    is_initial: bool = False
    is_final: bool = False

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Le nom d'un statut ne peut pas être vide.")
        return value


class StatusDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    color: str
    position: int
    is_initial: bool
    is_final: bool


class DueStepIn(BaseModel):
    """Un seuil d'échéance : « N jours restants ou moins » prend cette couleur."""

    days: int = Field(ge=1, le=3650)
    color: str = Field(pattern=HEX_COLOR_PATTERN)


class DueThresholdsIn(BaseModel):
    """Couleurs de l'échéance : loin, chaque seuil (du plus large au plus serré), dépassée."""

    far_color: str = Field(default="#18753c", pattern=HEX_COLOR_PATTERN)
    steps: list[DueStepIn] = Field(default_factory=list, max_length=5)
    overdue_color: str = Field(default="#8a0000", pattern=HEX_COLOR_PATTERN)

    @field_validator("steps")
    @classmethod
    def _steps_must_be_distinct(cls, steps: list[DueStepIn]) -> list[DueStepIn]:
        days = [step.days for step in steps]
        if len(set(days)) != len(days):
            raise ValueError("Deux seuils ne peuvent pas avoir le même nombre de jours.")
        return sorted(steps, key=lambda step: step.days, reverse=True)


class DueSettingsIn(BaseModel):
    # Durée par défaut, en jours depuis la création du dossier ; absente = pas d'échéance automatique.
    default_due_days: int | None = Field(default=None, ge=1, le=3650)
    thresholds: DueThresholdsIn


class DueSettingsOut(DueSettingsIn):
    pass


FIELD_ID_PATTERN = r"^f_[a-z0-9]{4,32}$"


class CustomFieldIn(BaseModel):
    """Définition d'une colonne personnalisée du suivi (issue #173). ``id`` absent : un nouveau champ, le serveur
    lui donne un identifiant stable (les valeurs des dossiers s'y rattachent)."""

    id: str | None = Field(default=None, pattern=FIELD_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    # Que représente le champ, comment le remplir : affichée en aide dans l'en-tête de la colonne.
    definition: str = Field(default="", max_length=500)
    type: Literal["text", "number", "amount", "date", "boolean", "choice"]
    required: bool = False
    default_value: Any = None
    choices: list[str] = Field(default_factory=list, max_length=50)
    currency: Literal["EUR", "USD", "GBP"] = "EUR"

    @field_validator("name")
    @classmethod
    def _strip_name(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Chaque champ doit avoir un nom.")
        return name

    @field_validator("choices")
    @classmethod
    def _clean_choices(cls, choices: list[str]) -> list[str]:
        cleaned = [choice.strip() for choice in choices if choice.strip()]
        if any(len(choice) > 80 for choice in cleaned):
            raise ValueError("Un choix est limité à 80 caractères.")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Deux choix ne peuvent pas être identiques.")
        return cleaned

    @model_validator(mode="after")
    def _coherent(self) -> "CustomFieldIn":
        if self.type == "choice" and not self.choices:
            raise ValueError(f"« {self.name} » : ajoutez au moins un choix.")
        if self.type != "choice":
            self.choices = []
        # La valeur par défaut doit convenir au type (jamais « obligatoire » ici : le défaut peut être vide).
        error = validate_value({**self.model_dump(), "required": False}, self.default_value)
        if error:
            raise ValueError(f"« {self.name} », valeur par défaut : {error}")
        return self


class CustomFieldOut(CustomFieldIn):
    id: str


class CustomFieldsUpdate(BaseModel):
    fields: list[CustomFieldIn] = Field(max_length=MAX_FIELDS_PER_ANALYSE)
    # Les champs supprimés gardent leurs valeurs (récupérables si le champ revient, par restauration) ; `true` les
    # supprime définitivement de tous les dossiers.
    purge_removed: bool = False

    @model_validator(mode="after")
    def _unique(self) -> "CustomFieldsUpdate":
        names = [field.name.lower() for field in self.fields]
        if len(set(names)) != len(names):
            raise ValueError("Deux champs ne peuvent pas porter le même nom.")
        ids = [field.id for field in self.fields if field.id]
        if len(set(ids)) != len(ids):
            raise ValueError("Deux champs ne peuvent pas avoir le même identifiant.")
        return self


class ClassificationOut(BaseModel):
    prompt: str
    prompt_versions: list[Version[str]]
    labels: list[LabelDefinitionOut]
    labels_versions: list[Version[list[LabelDefinitionOut]]]


class ExtractionOut(BaseModel):
    prompt: str
    prompt_versions: list[Version[str]]
    entities: list[EntityDefinitionOut]
    entities_versions: list[Version[list[EntityDefinitionOut]]]


class AgentCreate(BaseModel):
    name: str
    # La description est obligatoire : elle décrit précisément le but métier
    # de l'agent et sert de prompt au modèle de langage lors de l'exécution.
    prompt: str = Field(min_length=1)
    tools: list[AgentTool] = []
    output: bool = True
    # Identifiant de modèle tel que renvoyé par GET /models ; None = pas de
    # préférence, le hub par défaut sera utilisé.
    model: str | None = None

    @field_validator("prompt")
    @classmethod
    def _prompt_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("La description (prompt) ne peut pas être vide.")
        return value


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    prompt: str
    prompt_versions: list[Version[str]]
    tools: list[AgentTool]
    tools_versions: list[Version[list[AgentTool]]]
    output: bool
    output_versions: list[Version[bool]]
    model: str | None
    model_versions: list[Version[str | None]]


class AnalyseCreate(BaseModel):
    name: str
    # La description est obligatoire : elle décrit le but métier de
    # l'analyse et sert de prompt/instruction globale aux agents lors de
    # l'exécution.
    description: str = Field(min_length=1)

    @field_validator("description")
    @classmethod
    def _description_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("La description ne peut pas être vide.")
        return value


class AnalyseListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    created_at: datetime
    agent_count: int
    # Statuts de dossier de l'analyse (issue #168) : la liste des dossiers s'en sert pour son filtre.
    statuses: list["StatusDefinitionOut"] = []


class AnalyseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    created_at: datetime
    # Version courante (v1, v2...) : un dossier garde celle de son dernier lancement, ce qui permet de voir qu'il
    # a été traité avec une version plus ancienne.
    version: str
    classification: ClassificationOut
    extraction: ExtractionOut
    # Statuts de dossier de l'analyse (issue #168), dans l'ordre, et leurs versions précédentes.
    statuses: list[StatusDefinitionOut] = []
    statuses_versions: list[Version[list[StatusDefinitionOut]]] = []
    # Échéance des dossiers (issue #172) : durée par défaut et seuils de couleur, avec leur historique.
    due_settings: DueSettingsOut | None = None
    due_settings_versions: list[Version[DueSettingsOut]] = []
    # Colonnes personnalisées du suivi (issue #173) et leur historique.
    custom_fields: list[CustomFieldOut] = []
    custom_fields_versions: list[Version[list[CustomFieldOut]]] = []
    agents: list[AgentOut]


class PromptUpdate(BaseModel):
    prompt: str = Field(min_length=1)

    @field_validator("prompt")
    @classmethod
    def _prompt_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("La description (prompt) ne peut pas être vide.")
        return value


class LabelsUpdate(BaseModel):
    labels: list[LabelDefinitionIn]


class EntitiesUpdate(BaseModel):
    entities: list[EntityDefinitionIn]


class StatusesUpdate(BaseModel):
    statuses: list[StatusDefinitionIn]
    # Pour chaque statut supprimé encore utilisé par des dossiers : le statut qui les reprend.
    replacements: dict[uuid.UUID, uuid.UUID] = {}


class StatusesRestore(BaseModel):
    replacements: dict[uuid.UUID, uuid.UUID] = {}


class ToolsUpdate(BaseModel):
    tools: list[AgentTool]


class OutputUpdate(BaseModel):
    output: bool


class ModelUpdate(BaseModel):
    model: str | None


class AnalyseShareCreate(BaseModel):
    kind: AnalyseShareKind
    # kind == email :
    email: str | None = None
    expires_in_hours: int | None = None
    # kind == keycloak_group :
    keycloak_group: str | None = None


class AnalyseShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: AnalyseShareKind
    email: str | None
    keycloak_group: str | None
    expires_at: datetime | None
    created_by: str
    created_at: datetime
    # Uniquement renvoyé à la création d'un partage par email : le jeton en
    # clair n'est jamais stocké, donc jamais renvoyé ensuite.
    share_url: str | None = None
