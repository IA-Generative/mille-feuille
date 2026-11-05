import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _stripped(value: str) -> str:
    return value.strip()


class LlmCapabilityIn(BaseModel):
    name: str = Field(min_length=1, max_length=80, description="Par exemple « Tâches lourdes ».")
    description: str = Field(
        min_length=1,
        max_length=500,
        description="Ce que la capacité permet : lue par le modèle qui choisit le modèle d'une demande (mode auto).",
    )

    _strip = field_validator("name", "description")(_stripped)


class LlmCapabilityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, min_length=1, max_length=500)

    _strip = field_validator("name", "description")(lambda value: value.strip() if value else value)


class LlmCapabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str


class LlmModelCreate(BaseModel):
    name: str = Field(min_length=1, description="Le nom du modèle, tel que le hub le renvoie.")
    capability_ids: list[uuid.UUID] = Field(default_factory=list)
    enabled: bool = True

    _strip = field_validator("name")(_stripped)


class LlmModelUpdate(BaseModel):
    capability_ids: list[uuid.UUID] | None = None
    enabled: bool | None = None


class LlmModelOrder(BaseModel):
    model_ids: list[uuid.UUID] = Field(description="Tous les modèles, dans l'ordre voulu : le premier est le défaut.")


class LlmModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    position: int
    enabled: bool
    capability_ids: list[uuid.UUID]

    @classmethod
    def of(cls, model) -> "LlmModelOut":  # noqa: ANN001
        return cls(
            id=model.id,
            name=model.name,
            position=model.position,
            enabled=model.enabled,
            capability_ids=[capability.id for capability in model.capabilities],
        )


class LlmRoutingOut(BaseModel):
    auto_mode: bool


class LlmHubModelsOut(BaseModel):
    """Les noms que le hub sert et que la liste n'a pas encore, et quand le hub a été lu pour la dernière fois."""

    models: list[str]
    read_at: datetime
