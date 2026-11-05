import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.llm_model import MAX_LEVEL, MIN_LEVEL, LlmCapability


def _known(capabilities: list[LlmCapability] | None) -> list[str] | None:
    return None if capabilities is None else sorted({capability.value for capability in capabilities})


class LlmModelCreate(BaseModel):
    name: str = Field(min_length=1, description="Le nom du modèle, tel que le hub le renvoie (GET /models).")
    capabilities: list[LlmCapability] = Field(default_factory=lambda: [LlmCapability.COMPLETION])
    level: int = Field(default=MIN_LEVEL, ge=MIN_LEVEL, le=MAX_LEVEL, description="1 : léger, 3 : puissant.")
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class LlmModelUpdate(BaseModel):
    capabilities: list[LlmCapability] | None = None
    level: int | None = Field(default=None, ge=MIN_LEVEL, le=MAX_LEVEL)
    enabled: bool | None = None
    position: int | None = Field(default=None, ge=0)

    def changes(self) -> dict:
        changes = self.model_dump(exclude_none=True)
        if self.capabilities is not None:
            changes["capabilities"] = _known(self.capabilities)
        return changes


class LlmModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    capabilities: list[str]
    level: int
    position: int
    enabled: bool
