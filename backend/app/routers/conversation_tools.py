import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dossier_guard import require_dossier_visible
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.models.conversation import Conversation
from app.repositories.analyse_repository import AnalyseRepository
from app.repositories.dossier_repository import DossierRepository
from app.schemas.tool_call import ChatToolOut, ConversationToolsOut, ConversationToolsUpdate
from app.services.tools.conversation_tools import analysis_tool_ids, chat_tools_for
from app.services.tools.ids import unique

# Même garde que les routes `/dossiers/{id}/…` : 404 pour qui ne voit pas le dossier.
router = APIRouter(
    prefix="/dossiers", tags=["Tools"], dependencies=[Depends(get_current_user), Depends(require_dossier_visible)]
)


async def _own_conversation(db: AsyncSession, dossier_id: uuid.UUID, conversation_id: uuid.UUID, user: RequestContext):
    """La conversation de la personne, avec l'analyse du dossier ; 404 sinon (une conversation est personnelle)."""
    repository = DossierRepository(db)
    dossier = await repository.get(dossier_id, user)
    conversation = await repository.get_conversation(conversation_id)
    if (
        dossier is None
        or conversation is None
        or conversation.dossier_id != dossier_id
        or conversation.user_id != user.user_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation introuvable")
    analyse = await AnalyseRepository(db).get(dossier.analyse_id) if dossier.analyse_id else None
    return conversation, analyse


async def _view(db: AsyncSession, user: RequestContext, conversation: Conversation, analyse) -> ConversationToolsOut:
    view = await chat_tools_for(db, user, analyse) if analyse else None
    tools = view.tools if view else []
    return ConversationToolsOut(
        tools=[ChatToolOut(**vars(tool), given_to_model=tool.given_to_model) for tool in tools],
        excluded=list(conversation.excluded_tools),
        unavailable=view.unavailable if view else [],
    )


@router.get("/{dossier_id}/conversations/{conversation_id}/tools", response_model=ConversationToolsOut)
async def get_conversation_tools(
    dossier_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> ConversationToolsOut:
    """Les outils que l'analyse autorise pour cette conversation, et ceux que la personne a retirés."""
    conversation, analyse = await _own_conversation(db, dossier_id, conversation_id, user)
    return await _view(db, user, conversation, analyse)


@router.put("/{dossier_id}/conversations/{conversation_id}/tools", response_model=ConversationToolsOut)
async def update_conversation_tools(
    dossier_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: ConversationToolsUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> ConversationToolsOut:
    """Retire des outils pour cette conversation. Seuls des outils **de l'analyse** peuvent être retirés : un
    identifiant étranger est ignoré (on ne stocke pas n'importe quoi)."""
    conversation, analyse = await _own_conversation(db, dossier_id, conversation_id, user)
    allowed = set(analysis_tool_ids(analyse)) if analyse else set()
    conversation.excluded_tools = [tool_id for tool_id in unique(body.excluded) if tool_id in allowed]
    await db.commit()
    await db.refresh(conversation)
    return await _view(db, user, conversation, analyse)
