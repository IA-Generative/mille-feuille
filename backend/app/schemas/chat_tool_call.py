import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.chat_tool_call import ChatToolCallStatus

MAX_CALLS_PER_BATCH = 5


class ChatToolCallIn(BaseModel):
    """Un appel d'outil déposé par le worker avec le message de l'assistant : en attente de décision, ou déjà exécuté
    (un outil en lecture seule du même tour, dont le résultat sert à reconstruire l'historique)."""

    llm_call_id: str
    function_name: str
    tool_id: str
    tool_name: str = ""
    server_name: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    side_effect: bool = False
    status: Literal["pending", "executed"]
    result: str | None = None


class ChatToolCallOut(BaseModel):
    """Ce que la personne voit : l'outil, les arguments choisis par le modèle, et où en est la décision. Le résultat
    brut de l'outil n'est pas exposé : c'est la réponse de l'assistant qui le résume."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: uuid.UUID
    position: int
    tool_name: str
    server_name: str
    arguments: dict[str, Any]
    side_effect: bool
    status: ChatToolCallStatus
    decided_at: datetime | None


class InternalChatToolCallOut(BaseModel):
    """Ce que le worker lit pour reconstruire l'historique du modèle."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    llm_call_id: str
    function_name: str
    tool_id: str
    tool_name: str
    server_name: str
    arguments: dict[str, Any]
    status: ChatToolCallStatus
    result: str | None


MAX_COMMENT_LENGTH = 500


class ToolCallDecision(BaseModel):
    id: uuid.UUID
    allow: bool
    # Pour un refus : ce que la personne veut que l'assistant fasse à la place. Ignoré pour une autorisation.
    comment: str | None = Field(default=None, max_length=MAX_COMMENT_LENGTH)

    @field_validator("comment")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class ToolCallDecisions(BaseModel):
    """La décision d'un lot : **chaque** demande en attente du message, ensemble."""

    decisions: list[ToolCallDecision] = Field(min_length=1, max_length=MAX_CALLS_PER_BATCH)


class ToolCallResultIn(BaseModel):
    result: str
