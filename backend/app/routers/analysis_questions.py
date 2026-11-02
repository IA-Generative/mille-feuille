import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import get_current_user
from app.db import get_db
from app.models.analyse import Analyse, VersionedField
from app.repositories.analyse_repository import AnalyseRepository
from app.schemas.analyse import Version
from app.schemas.frequent_questions import FrequentQuestions, FrequentQuestionsOut

router = APIRouter(prefix="/analyses", tags=["Questions fréquentes"], dependencies=[Depends(get_current_user)])


async def _analyse_or_404(repository: AnalyseRepository, analyse_id: uuid.UUID) -> Analyse:
    analyse = await repository.get(analyse_id)
    if analyse is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analyse introuvable")
    return analyse


def _out(repository: AnalyseRepository, analyse: Analyse) -> FrequentQuestionsOut:
    return FrequentQuestionsOut(
        questions=list(analyse.frequent_questions),
        versions=[
            Version(id=v.id, content=FrequentQuestions(questions=list(v.content)), created_at=v.created_at)
            for v in repository.field_versions(analyse, VersionedField.FREQUENT_QUESTIONS)
        ],
    )


@router.get("/{analyse_id}/frequent-questions", response_model=FrequentQuestionsOut)
async def get_frequent_questions(
    analyse_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> FrequentQuestionsOut:
    """Les questions fréquentes de l'analyse et leur historique."""
    repository = AnalyseRepository(db)
    return _out(repository, await _analyse_or_404(repository, analyse_id))


@router.put("/{analyse_id}/frequent-questions", response_model=FrequentQuestionsOut)
async def update_frequent_questions(
    analyse_id: uuid.UUID, body: FrequentQuestions, db: Annotated[AsyncSession, Depends(get_db)]
) -> FrequentQuestionsOut:
    """Remplace la liste ; la précédente est conservée dans l'historique. Les dossiers déjà analysés reçoivent la
    réponse aux nouvelles questions à leur relance, pas avant."""
    repository = AnalyseRepository(db)
    analyse = await _analyse_or_404(repository, analyse_id)
    await repository.update_frequent_questions(analyse, body.questions)
    return _out(repository, analyse)


@router.post("/{analyse_id}/frequent-questions/restore/{version_id}", response_model=FrequentQuestionsOut)
async def restore_frequent_questions(
    analyse_id: uuid.UUID, version_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> FrequentQuestionsOut:
    """Restaure une liste antérieure ; la liste courante devient elle-même une version."""
    repository = AnalyseRepository(db)
    analyse = await _analyse_or_404(repository, analyse_id)
    version = repository.frequent_questions_version(analyse, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Version introuvable")
    await repository.update_frequent_questions(analyse, FrequentQuestions(questions=list(version.content)).questions)
    return _out(repository, analyse)
