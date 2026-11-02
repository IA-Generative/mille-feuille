import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.dispatch import dispatch_question_answers
from app.core.dossier_guard import require_dossier_visible
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.models.question_answer import DossierQuestionAnswer, QuestionAnswerStatus
from app.repositories.dossier_repository import DossierRepository
from app.schemas.question_answer import QuestionAnswerOut, QuestionAnswerSourceOut, QuestionAnswersOut

# Même garde que les routes `/dossiers/{id}/…` : 404 pour qui ne voit pas le dossier.
router = APIRouter(
    prefix="/dossiers",
    tags=["Questions fréquentes"],
    dependencies=[Depends(get_current_user), Depends(require_dossier_visible)],
)


async def _visible_dossier(db: AsyncSession, dossier_id: uuid.UUID, user: RequestContext) -> None:
    if await DossierRepository(db).get(dossier_id, user) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")


@router.get("/{dossier_id}/question-answers", response_model=QuestionAnswersOut)
async def list_question_answers(
    dossier_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> QuestionAnswersOut:
    """Les réponses prêtes aux questions fréquentes de l'analyse, dans l'ordre de l'analyse : elles s'affichent sans
    appel au modèle. Une question dont le dossier ne contient pas la réponse n'y figure pas."""
    await _visible_dossier(db, dossier_id, user)
    rows = (
        (
            await db.execute(
                select(DossierQuestionAnswer)
                .where(DossierQuestionAnswer.dossier_id == dossier_id)
                .order_by(DossierQuestionAnswer.position)
            )
        )
        .scalars()
        .all()
    )
    statuses = {row.status for row in rows}
    state = (
        "pending"
        if QuestionAnswerStatus.EN_COURS in statuses
        else "failed"
        if QuestionAnswerStatus.ECHEC in statuses
        else "ready"
    )
    return QuestionAnswersOut(
        status=state,
        answers=[
            QuestionAnswerOut(
                id=row.id,
                question=row.question,
                answer=row.answer or "",
                sources=[QuestionAnswerSourceOut.model_validate(source) for source in row.sources],
            )
            for row in rows
            if row.status == QuestionAnswerStatus.REPONDUE
        ],
    )


@router.post("/{dossier_id}/question-answers/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_question_answers(
    dossier_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> dict[str, str]:
    """Relance le calcul des réponses (la liste de l'analyse fait foi) : c'est ce qui reprend une réponse en échec.
    Les réponses à jour ne sont pas recalculées."""
    await _visible_dossier(db, dossier_id, user)
    dispatch_question_answers(str(dossier_id))
    return {"status": "started"}
