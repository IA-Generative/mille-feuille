import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.knowledge_source import KnowledgeSource
from app.models.tool import ToolAuthMode, ToolVisibility
from app.schemas.tool import ActiveAuthMode


class KnowledgeSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=2000)
    auth_mode: ActiveAuthMode = ToolAuthMode.TOKEN_EXCHANGE
    # Client Keycloak du fournisseur, obligatoire pour l'identité de l'utilisateur : le jeton est échangé pour lui.
    audience: str | None = Field(default=None, max_length=200)
    visibility: ToolVisibility = ToolVisibility.PRIVATE

    @model_validator(mode="after")
    def _audience_is_required_for_token_exchange(self) -> "KnowledgeSourceCreate":
        self.name = self.name.strip()
        self.audience = (self.audience or "").strip() or None
        if not self.name:
            raise ValueError("Le nom est obligatoire.")
        if self.auth_mode == ToolAuthMode.TOKEN_EXCHANGE and not self.audience:
            raise ValueError("L'audience Keycloak du fournisseur est obligatoire pour l'identité de l'utilisateur.")
        return self


class KnowledgeSourceOut(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    auth_mode: ToolAuthMode
    visibility: ToolVisibility
    audience: str | None = None
    owner_name: str
    owned_by_me: bool
    created_at: datetime

    @classmethod
    def of(cls, source: KnowledgeSource, *, user_id: str) -> "KnowledgeSourceOut":
        return cls(
            id=source.id,
            name=source.name,
            url=source.url,
            auth_mode=source.auth_mode,
            visibility=source.visibility,
            audience=source.audience,
            owner_name=source.owner_name,
            owned_by_me=source.created_by == user_id,
            created_at=source.created_at,
        )
