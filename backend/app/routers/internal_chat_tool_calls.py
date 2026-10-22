import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.internal import verify_app_token
from app.db import get_db
from app.models.chat_tool_call import ChatToolCallStatus
from app.repositories.chat_tool_call_repository import ChatToolCallRepository
from app.schemas.chat_tool_call import InternalChatToolCallOut, ToolCallResultIn

router = APIRouter(
    prefix="/internal/chat-tool-calls", tags=["Internal", "Tools"], dependencies=[Depends(verify_app_token)]
)


@router.post("/{call_id}/result", response_model=InternalChatToolCallOut)
async def record_tool_call_result(
    call_id: uuid.UUID, body: ToolCallResultIn, db: Annotated[AsyncSession, Depends(get_db)]
) -> InternalChatToolCallOut:
    """Le worker a exécuté un appel autorisé : on garde son résultat, que le modèle lira au prochain tour. Seul un appel
    **autorisé** s'enregistre (jamais un appel en attente, refusé ou laissé sans réponse)."""
    repository = ChatToolCallRepository(db)
    call = await repository.get(call_id)
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Appel introuvable")
    if call.status != ChatToolCallStatus.APPROVED:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Cet appel n'est pas autorisé")
    await repository.record_result(call, body.result)
    return InternalChatToolCallOut.model_validate(call)
