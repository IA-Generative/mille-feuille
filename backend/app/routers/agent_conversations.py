"""API REST produit pour l'agent helper (issue #50) : la modal ouverte
depuis le bouton près du profil (frontend, à venir) parle à ces routes,
authentifiées Keycloak comme le reste de l'API produit - contrairement à
/api/internal/agent/* (worker) et /mcp/helper (client MCP externe)."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.dispatch import dispatch_helper_chat_response
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.models.agent_conversation import AgentMessageRole
from app.repositories.agent_conversation_repository import AgentConversationRepository
from app.schemas.agent_conversation import (
    AgentChatEventOut,
    AgentConversationOut,
    AgentConversationSummaryOut,
    AgentMessageIn,
)
from app.schemas.pagination import Page

router = APIRouter(
    prefix="/agent-conversations",
    tags=["Agent"],
    dependencies=[Depends(get_current_user)],
)

# Longueur du titre auto-généré à partir du premier message (simple
# troncage pour la V1 - voir docs/mcp-helper-agent-plan.md, "points
# laissés ouverts" pour l'alternative appel LLM dédié).
_TITLE_MAX_LENGTH = 60


def _truncate_title(content: str) -> str:
    content = content.strip().replace("\n", " ")
    if len(content) <= _TITLE_MAX_LENGTH:
        return content
    return content[: _TITLE_MAX_LENGTH - 1].rstrip() + "…"


async def _get_owned_or_404(repository: AgentConversationRepository, conversation_id: uuid.UUID, user_id: str):
    conversation = await repository.get(conversation_id)
    if conversation is None or conversation.created_by != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable")
    return conversation


@router.get("", response_model=Page[AgentConversationSummaryOut])
async def list_my_agent_conversations(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[AgentConversationSummaryOut]:
    conversations, total = await AgentConversationRepository(db).list_for_user_paginated(
        created_by=user.user_id, page=page, page_size=page_size
    )
    items = [AgentConversationSummaryOut.from_conversation(c) for c in conversations]
    return Page.of(items, total=total, page=page, page_size=page_size)


@router.post("", response_model=AgentConversationOut, status_code=status.HTTP_201_CREATED)
async def create_agent_conversation(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AgentConversationOut:
    return await AgentConversationRepository(db).create(created_by=user.user_id)


@router.get("/{conversation_id}", response_model=AgentConversationOut)
async def get_agent_conversation(
    conversation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AgentConversationOut:
    repository = AgentConversationRepository(db)
    return await _get_owned_or_404(repository, conversation_id, user.user_id)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_conversation(
    conversation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> None:
    repository = AgentConversationRepository(db)
    conversation = await _get_owned_or_404(repository, conversation_id, user.user_id)
    await repository.delete(conversation)


@router.post("/{conversation_id}/messages", response_model=AgentConversationOut)
async def add_agent_conversation_message(
    conversation_id: uuid.UUID,
    body: AgentMessageIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AgentConversationOut:
    repository = AgentConversationRepository(db)
    conversation = await _get_owned_or_404(repository, conversation_id, user.user_id)
    # Nettoie les événements de chat de l'exécution précédente : le
    # frontend SSE ne doit voir que les événements de cette nouvelle
    # exécution (même raison que dossiers.py::add_message).
    await repository.delete_chat_events(conversation_id)
    if conversation.title is None:
        conversation = await repository.set_title(conversation, _truncate_title(body.content))
    conversation = await repository.add_message(conversation, AgentMessageRole.USER, content=body.content)
    # Déclenche la tâche Celery : le worker charge l'historique via
    # /internal/agent-conversations/{id}, exécute le graphe LangGraph de
    # l'agent helper, dépose les événements intermédiaires (agent_chat_events)
    # et le message assistant final (avec sources) via l'API interne.
    dispatch_helper_chat_response(str(conversation_id), model=body.model)
    return conversation


# --- SSE : streaming des événements de chat (même pattern que
# dossiers.py::stream_chat_events, voir son commentaire pour le détail) ---


async def _agent_chat_events(
    repository: AgentConversationRepository,
    conversation_id: uuid.UUID,
    user_id: str,
) -> AsyncIterator[str]:
    last_seen_id: uuid.UUID | None = None
    while True:
        conversation = await repository.get(conversation_id)
        if conversation is None or conversation.created_by != user_id:
            yield 'event: error\ndata: {"detail": "Conversation introuvable"}\n\n'
            return

        events = await repository.list_chat_events(conversation_id, after_id=last_seen_id)
        for event in events:
            last_seen_id = event.id
            payload = AgentChatEventOut.model_validate(event).model_dump(mode="json")
            data = json.dumps(payload)
            yield f"event: chat-event\ndata: {data}\n\n"
            # L'événement `done` ou `error` marque la fin du flux : on
            # émet un événement SSE `done` explicite pour que le frontend
            # (addEventListener('done', ...)) le capte avant la fermeture.
            if event.kind in ("done", "error"):
                yield "event: done\ndata: {}\n\n"
                return
        await asyncio.sleep(0.5)


@router.get("/{conversation_id}/stream")
async def stream_agent_chat_events(
    conversation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    repository = AgentConversationRepository(db)
    await _get_owned_or_404(repository, conversation_id, user.user_id)
    return StreamingResponse(
        _agent_chat_events(repository, conversation_id, user.user_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
