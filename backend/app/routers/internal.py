import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.dispatch import dispatch_document_summary, dispatch_index_document
from app.core.security.internal import verify_app_token
from app.db import get_db
from app.models.dossier import TextExtractionStatus
from app.models.dossier_analysis import AnalysisUnitStatus
from app.repositories.analyse_repository import AnalyseRepository
from app.repositories.document_draft_repository import (
    DocumentDraftRepository,
)
from app.repositories.dossier_analysis_repository import DossierAnalysisRepository
from app.repositories.dossier_repository import DossierRepository
from app.schemas.dossier import (
    BoundingBoxIn,
    BoundingBoxOut,
    DocumentPageIn,
    DocumentPageOut,
    DocumentPredictionIn,
    DocumentPredictionOut,
    DossierDocumentOut,
    ExecutionLogIn,
    ExecutionStepCompleteIn,
    ExecutionStepOut,
    FileHashIn,
    InternalAnalyseOut,
    InternalDossierOut,
    PageTextBoxIn,
    PageTextBoxOut,
    TextExtractionStatusIn,
)
from app.schemas.dossier_analysis import (
    AnalysisUnitCompleteIn,
    AnalysisUnitCreateIn,
    AnalysisUnitRefOut,
    ReusedEntity,
)
from app.schemas.user_task import UserTaskOut, UserTaskUpdateIn
from app.services import analysis_builder, analysis_carryover
from app.services.execution_steps import complete_step
from app.services.internal_analyse import build_internal_analyse
from app.services.user_task_service import update_task

# Routes appelées par les workers Celery (pas par le navigateur) : le worker
# dépose ici le résultat de son travail - logs en cours d'exécution, étape
# terminée, pages/prédictions extraites d'un document, réponse de l'agent.
router = APIRouter(prefix="/internal", tags=["Internal"], dependencies=[Depends(verify_app_token)])


@router.post("/execution-steps/{step_id}/logs", response_model=ExecutionStepOut)
async def add_execution_log(
    step_id: uuid.UUID,
    body: ExecutionLogIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repository = DossierRepository(db)
    step = await repository.get_execution_step_by_id(step_id)
    if step is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Étape introuvable")
    return await repository.add_log(step, body.level, body.message)


@router.post("/execution-steps/{step_id}/complete", response_model=ExecutionStepOut)
async def complete_execution_step(
    step_id: uuid.UUID,
    body: ExecutionStepCompleteIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    completed = await complete_step(db, step_id, body.status, body.output)
    if completed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Étape introuvable")
    return completed


@router.get("/documents/{document_id}", response_model=DossierDocumentOut)
async def get_document(document_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    document = await DossierRepository(db).get_document_by_id(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable")
    return document


@router.put("/documents/{document_id}/extraction-status", response_model=DossierDocumentOut)
async def set_document_extraction_status(
    document_id: uuid.UUID,
    body: TextExtractionStatusIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repository = DossierRepository(db)
    document = await repository.get_document_by_id(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable")
    await repository.set_text_extraction_status(document, body.status, body.error)
    if body.status == TextExtractionStatus.TERMINE and document.dossier_id:
        # Les pages sont écrites : le texte du document est résumé (issue #52) puis indexé dans la recherche du
        # dossier (découpage, embeddings, Qdrant).
        dispatch_document_summary(str(document.dossier_id), str(document.id))
        dispatch_index_document(str(document.dossier_id), str(document.id))
    return document


@router.put("/documents/{document_id}/file-hash", response_model=DossierDocumentOut)
async def set_document_file_hash(
    document_id: uuid.UUID,
    body: FileHashIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Dépose le hash SHA-256 d'un document, calculé par le worker
    document_process au moment de l'extraction (les bytes sont déjà en
    mémoire)."""
    repository = DossierRepository(db)
    document = await repository.get_document_by_id(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable")
    await repository.set_file_hash(document, body.file_hash)
    return document


@router.post(
    "/documents/{document_id}/pages",
    response_model=DocumentPageOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_document_page(
    document_id: uuid.UUID,
    body: DocumentPageIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repository = DossierRepository(db)
    document = await repository.get_document_by_id(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable")
    return await repository.add_page(
        document,
        page_number=body.page_number,
        width=body.width,
        height=body.height,
        content=body.content,
        screenshot_key=body.screenshot_key,
    )


@router.post(
    "/pages/{page_id}/bounding-boxes",
    response_model=BoundingBoxOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_bounding_box(
    page_id: uuid.UUID,
    body: BoundingBoxIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repository = DossierRepository(db)
    page = await repository.get_page_by_id(page_id)
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page introuvable")
    return await repository.add_bounding_box(page, **body.model_dump())


@router.put("/pages/{page_id}/text-boxes", response_model=list[PageTextBoxOut])
async def replace_page_text_boxes(
    page_id: uuid.UUID,
    body: list[PageTextBoxIn],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Remplace le texte positionné de la page (lignes et mots avec bbox et intervalle de caractères) : posé par
    document_process, lu par l'extraction pour localiser une valeur. Idempotent."""
    repository = DossierRepository(db)
    page = await repository.get_page_by_id(page_id)
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page introuvable")
    return await repository.replace_text_boxes(page, [box.model_dump() for box in body])


@router.get("/pages/{page_id}/text-boxes", response_model=list[PageTextBoxOut])
async def list_page_text_boxes(page_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    repository = DossierRepository(db)
    if await repository.get_page_by_id(page_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page introuvable")
    return await repository.list_text_boxes(page_id)


@router.post(
    "/pages/{page_id}/predictions",
    response_model=DocumentPredictionOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_document_prediction(
    page_id: uuid.UUID,
    body: DocumentPredictionIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repository = DossierRepository(db)
    page = await repository.get_page_by_id(page_id)
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page introuvable")
    analyses = DossierAnalysisRepository(db)
    unit = None
    if body.unit_id is not None:
        unit = await analyses.get_unit(body.unit_id)
        if unit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unité introuvable")
    prediction = await repository.add_prediction(
        page,
        kind=body.kind,
        name=body.name,
        value=body.value,
        confidence=body.confidence,
        source=body.source,
        label_definition_id=body.label_definition_id,
        entity_definition_id=body.entity_definition_id,
        page_ids=body.page_ids,
        bounding_box_ids=body.bounding_box_ids,
    )
    if unit is not None:
        # Analyse de dossier (#125) : un élément par prédiction.
        await analysis_builder.record_prediction(unit.id, prediction.id, page.id)
    return prediction


@router.post(
    "/dossiers/{dossier_id}/analysis-units",
    response_model=AnalysisUnitRefOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_analysis_unit(
    dossier_id: uuid.UUID,
    body: AnalysisUnitCreateIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Déclare une unité de calcul dans l'analyse courante du dossier. 404 si
    le dossier n'a pas d'analyse : le worker continue alors sans unité."""
    analyses = DossierAnalysisRepository(db)
    analysis = await analyses.get_current(dossier_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aucune analyse pour ce dossier")
    # Relance incrémentale (#119) : une unité dont l'empreinte est inchangée est
    # reprise de l'analyse précédente (éléments copiés), le worker ne la calcule pas.
    if body.input_fingerprint:
        reused = await analysis_carryover.reuse_unit(
            analyses,
            analysis,
            kind=body.kind,
            description=body.description,
            fingerprint=body.input_fingerprint,
        )
        if reused is not None:
            return AnalysisUnitRefOut(
                id=reused.unit.id,
                analysis_id=analysis.id,
                reused=True,
                reused_entities=[ReusedEntity(name=n, value=v) for n, v in reused.entities],
            )
    unit = await analyses.create_unit(
        analysis.id, kind=body.kind, description=body.description, input_fingerprint=body.input_fingerprint
    )
    return AnalysisUnitRefOut(id=unit.id, analysis_id=unit.analysis_id)


@router.post("/analysis-units/{unit_id}/complete", response_model=AnalysisUnitRefOut)
async def complete_analysis_unit(
    unit_id: uuid.UUID,
    body: AnalysisUnitCompleteIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    analyses = DossierAnalysisRepository(db)
    unit = await analyses.get_unit(unit_id)
    if unit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unité introuvable")
    status_value = AnalysisUnitStatus.TERMINE if body.status == "terminé" else AnalysisUnitStatus.ECHEC
    return await analyses.set_unit_status(unit, status_value)


@router.get("/dossiers/{dossier_id}", response_model=InternalDossierOut)
async def get_internal_dossier(dossier_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    """Dossier complet pour le worker agent_execution : documents, pages
    (avec clés S3 des captures), étapes d'exécution. Réservé à l'API
    interne - ne renvoie jamais les clés S3 côté frontend."""
    dossier = await DossierRepository(db).get(dossier_id)
    if dossier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")
    return dossier


@router.get("/analyses/{analyse_id}", response_model=InternalAnalyseOut)
async def get_internal_analyse(analyse_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    """Définitions de l'analyse (labels, entités, prompts de classification
    et d'extraction) pour les workers. Réservé à l'API interne."""
    analyse = await AnalyseRepository(db).get(analyse_id)
    if analyse is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analyse introuvable")
    return build_internal_analyse(analyse)


@router.put("/user-tasks/{task_id}", response_model=UserTaskOut)
async def update_user_task(
    task_id: uuid.UUID,
    body: UserTaskUpdateIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Callback interne : un worker met à jour le statut d'une tâche
    utilisateur (PENDING → RUNNING → SUCCESS/FAILURE). Appelé par les
    workers via l'API interne, authentifié par app token."""
    task = await update_task(db, task_id, body)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tâche introuvable")
    return task


# --- Génération des valeurs d'un brouillon de document (issue #141) ---


async def _draft_or_404(db: AsyncSession, draft_id: uuid.UUID):
    draft = await DocumentDraftRepository(db).get_by_id(draft_id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brouillon introuvable")
    return draft
