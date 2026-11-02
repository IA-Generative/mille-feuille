"""La présentation d'un dossier : ce que la conversation montre en tête (issue #423).

Composée à la demande, à partir de ce que l'analyse a déjà produit (résumé, classification, entités retenues, synthèses
des agents, réponses prêtes) : aucun appel au modèle, et toujours à jour (relance, correction)."""

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dossier import Dossier, DossierStatus, ExecutionStepKind
from app.models.dossier_analysis import AnalysisElementKind
from app.models.question_answer import DossierQuestionAnswer, QuestionAnswerStatus
from app.models.summary import SummaryStatus
from app.repositories.analyse_repository import AnalyseRepository
from app.repositories.dossier_analysis_repository import DossierAnalysisRepository
from app.schemas.dossier_presentation import (
    DossierPresentationOut,
    PresentationAgentOut,
    PresentationClassificationOut,
    PresentationDocumentOut,
    PresentationEntityOut,
    SuggestedQuestionOut,
)
from app.schemas.question_answer import QuestionAnswerSourceOut

# « Demande de logement (confiance : 94%) » : la sortie de l'étape de classification, lue comme le faisaient les cartes de résultats.
_CONFIDENCE = re.compile(r"^(.*) \(confiance : (\d+)%\)$")

_STATUS = {
    DossierStatus.EN_COURS: "pending",
    DossierStatus.TERMINE: "ready",
    DossierStatus.ECHEC: "failed",
}


def _classification(dossier: Dossier) -> PresentationClassificationOut | None:
    step = next((s for s in dossier.execution_steps if s.kind == ExecutionStepKind.CLASSIFICATION and s.output), None)
    if step is None:
        return None
    match = _CONFIDENCE.match(step.output)
    if match:
        return PresentationClassificationOut(label=match.group(1), confidence=int(match.group(2)))
    return PresentationClassificationOut(label=step.output)


async def _entities(db: AsyncSession, dossier: Dossier) -> list[PresentationEntityOut]:
    """Les entités retenues de l'analyse du dossier : une correction de l'instructeur fait foi."""
    repository = DossierAnalysisRepository(db)
    analysis = await repository.get_current(dossier.id)
    if analysis is None:
        return []
    elements = (await repository.build_out(analysis)).elements
    entities: list[PresentationEntityOut] = []
    for element in elements:
        if element.kind != AnalysisElementKind.ENTITY or element.retained_version is None:
            continue
        value = str((element.retained_version.value or {}).get("value", "")).strip()
        if value:
            entities.append(
                PresentationEntityOut(name=element.definition_name or "", value=value, page=element.first_page_number)
            )
    return entities


async def _suggestions(db: AsyncSession, dossier: Dossier) -> list[SuggestedQuestionOut]:
    rows = (
        (
            await db.execute(
                select(DossierQuestionAnswer)
                .where(
                    DossierQuestionAnswer.dossier_id == dossier.id,
                    DossierQuestionAnswer.status == QuestionAnswerStatus.REPONDUE,
                )
                .order_by(DossierQuestionAnswer.position)
            )
        )
        .scalars()
        .all()
    )
    return [
        SuggestedQuestionOut(
            id=row.id,
            question=row.question,
            answer=row.answer or "",
            sources=[QuestionAnswerSourceOut.model_validate(source) for source in row.sources],
        )
        for row in rows
    ]


async def _is_refreshing(db: AsyncSession, dossier: Dossier) -> bool:
    """Le résumé ou les réponses prêtes se calculent après la fin de l'analyse : tant que c'est le cas, la présentation
    n'est pas complète. Sans réponse du tout alors que l'analyse a des questions, le calcul n'a pas encore commencé."""
    if dossier.summary_status == SummaryStatus.EN_COURS:
        return True
    rows = (
        (await db.execute(select(DossierQuestionAnswer.status).where(DossierQuestionAnswer.dossier_id == dossier.id)))
        .scalars()
        .all()
    )
    if QuestionAnswerStatus.EN_COURS in rows:
        return True
    analyse = await AnalyseRepository(db).get(dossier.analyse_id) if dossier.analyse_id else None
    return bool(analyse and analyse.frequent_questions and not rows)


async def build_presentation(db: AsyncSession, dossier: Dossier) -> DossierPresentationOut:
    status = _STATUS.get(dossier.status, "idle")
    documents = [
        PresentationDocumentOut(
            id=document.id, name=document.name, label=document.label, page_count=len(document.pages)
        )
        for document in dossier.documents
    ]
    if status in ("idle", "pending"):
        # Pas de résumé partiel ni de suggestions tant que l'analyse n'est pas terminée.
        return DossierPresentationOut(status=status, dossier_name=dossier.name, documents=documents)
    if status == "failed":
        failed = next((s for s in dossier.execution_steps if s.output and s.status.value == "échec"), None)
        return DossierPresentationOut(
            status="failed",
            error=failed.output if failed else "L'analyse n'a pas pu aller à son terme.",
            dossier_name=dossier.name,
            documents=documents,
        )
    return DossierPresentationOut(
        status="ready",
        refreshing=await _is_refreshing(db, dossier),
        dossier_name=dossier.name,
        summary=dossier.summary.content if dossier.summary else None,
        summary_error=(dossier.summary_error or "Le résumé n'a pas pu être généré.")
        if dossier.summary_status == SummaryStatus.ECHEC
        else None,
        classification=_classification(dossier),
        entities=await _entities(db, dossier),
        agents=[
            PresentationAgentOut(name=step.label, output=step.output)
            for step in dossier.execution_steps
            if step.kind == ExecutionStepKind.AGENT and step.output
        ],
        documents=documents,
        suggestions=await _suggestions(db, dossier),
    )
