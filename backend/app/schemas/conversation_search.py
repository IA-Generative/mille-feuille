import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.conversation import MessageRole


class ConversationSearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


class ExcerptSegmentOut(BaseModel):
    text: str
    highlighted: bool


class ConversationMatchOut(BaseModel):
    """Le message le plus récent de la conversation qui correspond."""

    message_id: uuid.UUID
    role: MessageRole
    created_at: datetime
    excerpt: list[ExcerptSegmentOut]


class ConversationSearchResultOut(BaseModel):
    conversation_id: uuid.UUID
    dossier_id: uuid.UUID
    dossier_name: str
    # Date du message trouvé, ou de la dernière activité quand seul le nom du dossier correspond.
    date: datetime
    match: ConversationMatchOut | None
    match_count: int
