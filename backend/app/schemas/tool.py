import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.models.tool import Tool, ToolAuthMode, ToolServer, ToolVisibility
from app.services.tools.internal_catalog import InternalTool


def _refuse_static_token(mode: ToolAuthMode) -> ToolAuthMode:
    if mode == ToolAuthMode.STATIC_TOKEN:
        raise ValueError("Le jeton statique n'est pas encore disponible.")
    return mode


# Les modes d'authentification activables aujourd'hui ; `static_token` existe dans le modèle mais est refusé ici.
ActiveAuthMode = Annotated[ToolAuthMode, AfterValidator(_refuse_static_token)]


class ToolOut(BaseModel):
    id: str
    name: str
    description: str
    kind: Literal["internal", "mcp"]
    server_id: uuid.UUID | None = None
    side_effect: bool
    # Autorisé par la personne qui a ajouté le serveur (toujours vrai pour un tool interne).
    enabled: bool = True
    config: str | None = None

    @classmethod
    def of_internal(cls, tool: InternalTool) -> "ToolOut":
        return cls(
            id=tool.id,
            name=tool.name,
            description=tool.description,
            kind="internal",
            side_effect=tool.side_effect,
            config=tool.config,
        )

    @classmethod
    def of_mcp(cls, tool: Tool) -> "ToolOut":
        return cls(
            id=str(tool.id),
            name=tool.name,
            description=tool.description,
            kind="mcp",
            server_id=tool.server_id,
            side_effect=tool.side_effect,
            enabled=tool.enabled,
        )


class ToolServerOut(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    auth_mode: ToolAuthMode
    visibility: ToolVisibility
    audience: str | None = None
    owner_name: str
    owned_by_me: bool
    synced_at: datetime
    tools: list[ToolOut]

    @classmethod
    def of(cls, server: ToolServer, *, user_id: str) -> "ToolServerOut":
        return cls(
            id=server.id,
            name=server.name,
            url=server.url,
            auth_mode=server.auth_mode,
            visibility=server.visibility,
            audience=server.audience,
            owner_name=server.owner_name,
            owned_by_me=server.created_by == user_id,
            synced_at=server.synced_at,
            tools=[ToolOut.of_mcp(tool) for tool in server.tools],
        )


class DiscoverIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    auth_mode: ActiveAuthMode = ToolAuthMode.TOKEN_EXCHANGE
    # Client Keycloak du serveur, obligatoire pour l'identité de l'utilisateur : le jeton est échangé pour lui.
    audience: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _audience_is_required_for_token_exchange(self) -> "DiscoverIn":
        self.audience = (self.audience or "").strip() or None
        if self.auth_mode == ToolAuthMode.TOKEN_EXCHANGE and not self.audience:
            raise ValueError("L'audience Keycloak du serveur est obligatoire pour l'identité de l'utilisateur.")
        return self


class DiscoveredToolOut(BaseModel):
    name: str
    description: str
    side_effect: bool


class DiscoverOut(BaseModel):
    tools: list[DiscoveredToolOut]


class ToolServerCreate(DiscoverIn):
    name: str = Field(min_length=1, max_length=100)
    visibility: ToolVisibility = ToolVisibility.PRIVATE
    # Les tools que la personne autorise parmi ceux que le serveur expose.
    tool_names: list[str] = Field(min_length=1)
