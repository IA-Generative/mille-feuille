import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dossier_guard import require_dossier_visible
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.models.conversation import MessageRole
from app.models.question_answer import DossierQuestionAnswer, QuestionAnswerStatus
from app.repositories.dossier_repository import DossierRepository
from app.schemas.dossier import MessageOut
from app.schemas.dossier_presentation import DossierPresentationOut
from app.services.dossier_presentation import build_presentation

# Même garde que les routes `/dossiers/{id}/…` : 404 pour qui ne voit pas le dossier.
router = APIRouter(
    prefix="/dossiers",
    tags=["Présentation"],
    dependencies=[Depends(get_current_user), Depends(require_dossier_visible)],
)


@router.get("/{dossier_id}/presentation", response_model=DossierPresentationOut)
async def get_presentation(
    dossier_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> DossierPresentationOut:
    """La présentation du dossier, en tête de sa conversation : résumé, classification, informations clés, synthèses des
    agents, documents et questions dont la réponse est déjà prête. Aucun appel au modèle."""
    dossier = await DossierRepository(db).get(dossier_id, user)
    if dossier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")
    return await build_presentation(db, dossier)


@router.post(
    "/{dossier_id}/conversations/{conversation_id}/question-answers/{answer_id}/ask", response_model=list[MessageOut]
)
async def ask_prepared_question(
    dossier_id: uuid.UUID,
    conversation_id: uuid.UUID,
    answer_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> list:
    """Pose une question suggérée : la question et sa réponse prête entrent dans la conversation de la personne,
    comme un échange normal (avec les sources de la réponse). Aucun appel au modèle."""
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
    prepared = await db.get(DossierQuestionAnswer, answer_id)
    if prepared is None or prepared.dossier_id != dossier_id or prepared.status != QuestionAnswerStatus.REPONDUE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Réponse introuvable")
    await repository.add_message(conversation, MessageRole.USER, prepared.question)
    conversation = await repository.add_message(
        conversation, MessageRole.ASSISTANT, prepared.answer or "", sources=list(prepared.sources)
    )
    messages = conversation.messages[-2:]
    for message in messages:
        message.feedback = None
    return messages
