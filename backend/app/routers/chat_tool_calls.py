import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_client import dispatch_chat_response
from app.core.dossier_guard import require_dossier_visible
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.repositories.dossier_repository import DossierRepository
from app.schemas.chat_tool_call import ChatToolCallOut, ToolCallDecisions
from app.services.chat_tool_calls import DecisionError, decide_batch

# Même garde que les routes `/dossiers/{id}/…` : 404 pour qui ne voit pas le dossier.
router = APIRouter(
    prefix="/dossiers", tags=["Tools"], dependencies=[Depends(get_current_user), Depends(require_dossier_visible)]
)


@router.post("/{dossier_id}/conversations/{conversation_id}/tool-calls/decisions", response_model=list[ChatToolCallOut])
async def decide_tool_calls(
    dossier_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: ToolCallDecisions,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> list[ChatToolCallOut]:
    """La décision d'un lot d'appels d'outils : **chaque** demande en attente d'un message, ensemble. Elle relance le
    chat, qui exécute ce qui est autorisé puis reprend la discussion là où elle s'était arrêtée.

    Possible tant qu'aucun autre message n'a été envoyé ; ensuite la demande est « sans réponse » (409)."""
    repository = DossierRepository(db)
    conversation = await repository.get_conversation(conversation_id)
    if conversation is None or conversation.dossier_id != dossier_id or conversation.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation introuvable")
    try:
        calls = await decide_batch(db, conversation_id, body.decisions, user_id=user.user_id)
    except DecisionError as error:
        code = status.HTTP_409_CONFLICT if error.conflict else status.HTTP_422_UNPROCESSABLE_CONTENT
        raise HTTPException(code, detail={"code": error.code, "message": error.message}) from error
    # Le frontend ne doit voir que les événements de la nouvelle exécution (comme à l'envoi d'un message).
    await repository.delete_chat_events(conversation_id)
    dispatch_chat_response(str(conversation_id), str(dossier_id))
    return [ChatToolCallOut.model_validate(call) for call in calls]
