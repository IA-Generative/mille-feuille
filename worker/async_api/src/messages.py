"""Contrat d'entrée de la tâche (à garder aligné avec `contrat.json` : les tests le vérifient).

Ce que la plateforme n'ouvre pas, à dessein : `persist` (un consommateur ne stocke rien dans
mille-feuille — le résultat est rendu dans la réponse et le run supprimé), les outils d'agent
qui sortent du dossier (`OutilAgent`), et un `ttl_hours` au-delà de sept jours.
"""

import uuid
from typing import Self

from millefeuille.models import AgentCreate, AgentTool, EntityDefinitionIn, LabelDefinitionIn
from millefeuille_ephemeral import EphemeralAnalysisConfig
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.config import MAX_FILES_PLATEFORME, TTL_DEFAUT_PLATEFORME, TTL_MAX_PLATEFORME
from src.enums import OutilAgent

#: Un run de plateforme n'est jamais conservé : le résultat est dans le message `success`.
PERSIST_PLATEFORME = False


class _Entree(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FileRef(_Entree):
    # Clé S3 du fichier, déposé au préalable dans le stockage d'AsyncTaskAPI.
    file_id: str = Field(min_length=1, max_length=1024)
    # Nom d'affichage côté mille-feuille ; par défaut, le dernier segment de `file_id`.
    name: str | None = Field(default=None, min_length=1, max_length=255)

    @property
    def display_name(self) -> str:
        return self.name or self.file_id.rsplit("/", 1)[-1]


class AgentDefinition(_Entree):
    """Miroir d'`AgentCreate` du SDK, les outils restreints à ceux de la plateforme."""

    name: str = Field(min_length=1, max_length=255)
    prompt: str = Field(min_length=1, max_length=16000)
    tools: list[OutilAgent] = []
    output: bool = True
    model: str | None = Field(default=None, max_length=255)

    @field_validator("prompt")
    @classmethod
    def _prompt_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("La consigne de l'agent ne peut pas être vide.")
        return value

    def vers_sdk(self) -> AgentCreate:
        return AgentCreate(
            name=self.name,
            prompt=self.prompt,
            tools=[AgentTool(outil.value) for outil in self.tools],
            output=self.output,
            model=self.model,
        )


class AnalysisDefinition(_Entree):
    """Miroir d'`EphemeralAnalysisConfig` du SDK, sans `persist` : un test tient la dérive entre les deux."""

    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    classification_prompt: str = Field(default="", max_length=8000)
    multi_label: bool = False
    labels: list[LabelDefinitionIn] = Field(default=[], max_length=100)
    extraction_prompt: str = Field(default="", max_length=8000)
    entities: list[EntityDefinitionIn] = Field(default=[], max_length=100)
    agents: list[AgentDefinition] = Field(default=[], max_length=20)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Le nom de l'analyse ne peut pas être vide.")
        return value

    def vers_config(self) -> EphemeralAnalysisConfig:
        return EphemeralAnalysisConfig(
            name=self.name,
            description=self.description,
            persist=PERSIST_PLATEFORME,
            classification_prompt=self.classification_prompt,
            multi_label=self.multi_label,
            labels=self.labels,
            extraction_prompt=self.extraction_prompt,
            entities=self.entities,
            agents=[agent.vers_sdk() for agent in self.agents],
        )


class AnalyzeRequest(_Entree):
    # Définition complète créée à la volée, OU identifiant d'une analyse existante : exactement un des deux.
    analysis: AnalysisDefinition | None = None
    analyse_id: uuid.UUID | None = None
    files: list[FileRef] = Field(min_length=1, max_length=MAX_FILES_PLATEFORME)
    ttl_hours: int = Field(default=TTL_DEFAUT_PLATEFORME, ge=1, le=TTL_MAX_PLATEFORME)

    @model_validator(mode="after")
    def _exactly_one_analysis_source(self) -> Self:
        if (self.analysis is None) == (self.analyse_id is None):
            raise ValueError("Fournir exactement un de `analysis` ou `analyse_id`.")
        return self
