import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.internal import verify_app_token
from app.db import get_db
from app.models.conversation import MessageRole
from app.models.dossier import DossierStatus, ExecutionStep
from app.models.dossier_analysis import AnalysisUnitStatus, DossierAnalysisStatus
from app.repositories.analyse_repository import AnalyseRepository
from app.repositories.analysis_proposal_repository import AnalysisProposalRepository, ProposalTargetError
from app.repositories.document_draft_repository import (
    DocumentDraftRepository,
    DraftError,
    UnknownFieldError,
    ValidatedFieldError,
    template_definitions,
)
from app.repositories.dossier_analysis_repository import DossierAnalysisRepository
from app.repositories.dossier_note_repository import DossierNoteRepository
from app.repositories.dossier_repository import DossierRepository
from app.repositories.ephemeral_repository import EphemeralRepository
from app.schemas.analysis_proposal import InternalProposalCreateIn, ProposalOut
from app.schemas.document_draft import (
    FieldVersionOut,
    InternalDraftContextOut,
    InternalDraftNoteOut,
    InternalElementOut,
    InternalFieldOut,
    InternalGenerationIn,
    InternalProposeIn,
)
from app.schemas.dossier import (
    BoundingBoxIn,
    BoundingBoxOut,
    ChatEventIn,
    ChatEventOut,
    DocumentPageIn,
    DocumentPageOut,
    DocumentPredictionIn,
    DocumentPredictionOut,
    DossierDocumentOut,
    DossierSummaryOut,
    ExecutionLogIn,
    ExecutionStepCompleteIn,
    ExecutionStepOut,
    FileHashIn,
    InternalAgentOut,
    InternalAnalyseOut,
    InternalClassificationOut,
    InternalConversationOut,
    InternalDossierOut,
    InternalEntityDefinitionOut,
    InternalExtractionOut,
    InternalLabelDefinitionOut,
    InternalMessageIn,
    MessageOut,
    SuggestionDepositIn,
    SuggestionStatusIn,
    SummaryDepositIn,
    SummaryStatusIn,
    TextExtractionStatusIn,
)
from app.schemas.dossier_analysis import (
    AgentReuseIn,
    AgentReuseOut,
    AnalysisUnitCompleteIn,
    AnalysisUnitCreateIn,
    AnalysisUnitRefOut,
    DossierAnalysisOut,
    InvalidElementValueError,
    ReusedEntity,
)
from app.schemas.dossier_note import InternalNoteAnalysisIn, InternalNoteCreateIn, InternalNoteOut
from app.schemas.user_task import UserTaskOut, UserTaskUpdateIn
from app.services import analysis_builder, analysis_carryover, generation_prompt
from app.services.document_fields import FieldValueError, load_revision_elements
from app.services.ephemeral_run_service import finalize_run
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
    repository = DossierRepository(db)
    step = await repository.get_execution_step_by_id(step_id)
    if step is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Étape introuvable")
    completed = await repository.complete_execution_step(step, body.status, body.output)
    # Analyse de dossier (#125) : n'empêche jamais l'étape de se terminer.
    await analysis_builder.record_step_result(step_id)
    # Pose du TTL dès que le Dossier vient de passer à un état terminal (cf.
    # docs/ephemeral-api.md) - no-op immédiat si ce n'est pas encore le cas
    # (mark_dossier_terminal vérifie ended_at) ou si le dossier n'est pas
    # éphémère.
    dossier = await repository.get(completed.dossier_id)
    if dossier is not None and dossier.status != DossierStatus.EN_COURS:
        await EphemeralRepository(db).mark_dossier_terminal(dossier)
        # Run éphémère persist=false : on garde le résultat, on supprime dossier et analyse.
        # `completed` est sérialisé après ; il a déjà été chargé (logs comprises) avant.
        await finalize_run(db, dossier.id)
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


@router.put("/documents/{document_id}/summary-status", response_model=DossierDocumentOut)
async def set_document_summary_status(
    document_id: uuid.UUID,
    body: SummaryStatusIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Met à jour le statut de génération du résumé d'un document."""
    repository = DossierRepository(db)
    document = await repository.get_document_by_id(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable")
    await repository.set_document_summary_status(document, body.status, body.error)
    return document


@router.post(
    "/documents/{document_id}/summaries",
    response_model=DossierSummaryOut,
    status_code=status.HTTP_201_CREATED,
)
async def deposit_document_summary(
    document_id: uuid.UUID,
    body: SummaryDepositIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Dépose un nouveau résumé pour un document (append-only). Le worker
    appelle cette route après génération du résumé via LLM."""
    repository = DossierRepository(db)
    document = await repository.get_document_by_id(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable")
    return await repository.add_document_summary(document, content=body.content, model=body.model)


@router.put("/dossiers/{dossier_id}/summary-status", response_model=InternalDossierOut)
async def set_dossier_summary_status(
    dossier_id: uuid.UUID,
    body: SummaryStatusIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Met à jour le statut de génération du résumé global d'un dossier."""
    repository = DossierRepository(db)
    dossier = await repository.get(dossier_id)
    if dossier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")
    await repository.set_dossier_summary_status(dossier, body.status, body.error)
    return dossier


@router.post(
    "/dossiers/{dossier_id}/summaries",
    response_model=DossierSummaryOut,
    status_code=status.HTTP_201_CREATED,
)
async def deposit_dossier_summary(
    dossier_id: uuid.UUID,
    body: SummaryDepositIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Dépose un nouveau résumé global pour un dossier (append-only). Le
    worker appelle cette route après génération du résumé via LLM."""
    repository = DossierRepository(db)
    dossier = await repository.get(dossier_id)
    if dossier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")
    return await repository.add_dossier_summary(dossier, content=body.content, model=body.model)


@router.put("/dossiers/{dossier_id}/suggestion-status", response_model=InternalDossierOut)
async def set_dossier_suggestion_status(
    dossier_id: uuid.UUID,
    body: SuggestionStatusIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Met à jour le statut de génération des suggestions d'analyse d'un
    dossier « à ranger » (issue #54)."""
    repository = DossierRepository(db)
    dossier = await repository.get(dossier_id)
    if dossier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")
    await repository.set_suggestion_status(dossier, body.status, body.error)
    return dossier


@router.post(
    "/dossiers/{dossier_id}/suggestions",
    response_model=InternalDossierOut,
    status_code=status.HTTP_200_OK,
)
async def deposit_dossier_suggestions(
    dossier_id: uuid.UUID,
    body: SuggestionDepositIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Dépose les suggestions d'analyse générées par le LLM pour un dossier
    « à ranger » (issue #54). Le worker appelle cette route après avoir
    comparé les résumés du dossier avec les analyses disponibles."""
    repository = DossierRepository(db)
    dossier = await repository.get(dossier_id)
    if dossier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")
    await repository.set_suggested_analyses(dossier, body.suggestions)
    return dossier


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


@router.get("/dossiers/{dossier_id}/analysis", response_model=DossierAnalysisOut)
async def get_current_analysis(dossier_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    """Analyse courante du dossier avec ses éléments : le chat s'en sert pour
    savoir ce qu'il peut proposer de modifier. 404 si le dossier n'en a pas."""
    analyses = DossierAnalysisRepository(db)
    analysis = await analyses.get_current(dossier_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aucune analyse pour ce dossier")
    return await analyses.build_out(analysis)


@router.post(
    "/dossiers/{dossier_id}/analysis/proposals",
    response_model=ProposalOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_analysis_proposal(
    dossier_id: uuid.UUID,
    body: InternalProposalCreateIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Dépose une proposition de modification de l'analyse courante pour le
    compte d'un utilisateur. N'applique rien : l'utilisateur la valide."""
    analyses = DossierAnalysisRepository(db)
    analysis = await analyses.get_current(dossier_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aucune analyse pour ce dossier")
    if analysis.status == DossierAnalysisStatus.FIGEE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cette analyse est figée")
    try:
        return await AnalysisProposalRepository(analyses).create(
            analysis,
            proposed_by=body.proposed_by,
            value=body.value,
            reason=body.reason,
            element_id=body.element_id,
            kind=body.kind,
            definition_name=body.definition_name,
            source_type=body.source_type,
            source_id=body.source_id,
            model=body.model,
            prompt_version=body.prompt_version,
        )
    except ProposalTargetError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except InvalidElementValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


def _internal_note(note) -> InternalNoteOut:
    return InternalNoteOut(
        id=note.id,
        dossier_id=note.dossier_id,
        content=note.current.content,
        version_number=note.current.version_number,
        archived=note.archived,
        analysis_requested_by=note.analysis_requested_by,
    )


@router.get("/dossiers/{dossier_id}/notes", response_model=list[InternalNoteOut])
async def list_dossier_notes(dossier_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    """Notes internes (non archivées) d'un dossier : contexte du chat (issue #117)."""
    notes = await DossierNoteRepository(db).list(dossier_id)
    return [_internal_note(note) for note in notes]


@router.post("/dossiers/{dossier_id}/notes", response_model=InternalNoteOut, status_code=status.HTTP_201_CREATED)
async def create_dossier_note(
    dossier_id: uuid.UUID, body: InternalNoteCreateIn, db: Annotated[AsyncSession, Depends(get_db)]
):
    """Le chat du dossier ajoute une note interne à la demande de l'utilisateur (``author`` : ``chat-agent:<id>``)."""
    if await DossierRepository(db).get(dossier_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")
    note = await DossierNoteRepository(db).create(dossier_id, content=body.content.strip(), user_id=body.author)
    return _internal_note(note)


@router.get("/notes/{note_id}", response_model=InternalNoteOut)
async def get_dossier_note(note_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    note = await DossierNoteRepository(db).get_by_id(note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note introuvable")
    return _internal_note(note)


@router.post("/notes/{note_id}/analysis", response_model=InternalNoteOut)
async def finish_note_analysis(
    note_id: uuid.UUID, body: InternalNoteAnalysisIn, db: Annotated[AsyncSession, Depends(get_db)]
):
    """Le worker signale la fin de l'analyse d'une note (terminée ou en échec)."""
    repository = DossierNoteRepository(db)
    note = await repository.get_by_id(note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note introuvable")
    return _internal_note(
        await repository.finish_analysis(note, status=body.status, proposal_count=body.proposal_count, error=body.error)
    )


@router.post("/dossiers/{dossier_id}/agent-units/reuse", response_model=AgentReuseOut)
async def reuse_agent_unit(dossier_id: uuid.UUID, body: AgentReuseIn, db: Annotated[AsyncSession, Depends(get_db)]):
    """Relance incrémentale (#119) : l'agent d'une étape peut-il reprendre la
    synthèse de l'analyse précédente ? Oui si son empreinte (configuration et ce
    qu'il lit) est inchangée ; le worker dépose alors cette synthèse sans appeler le
    LLM. À appeler une fois la classification et l'extraction terminées."""
    analyses = DossierAnalysisRepository(db)
    analysis = await analyses.get_current(dossier_id)
    step = await db.get(ExecutionStep, body.step_id)
    if analysis is None or step is None or step.dossier_id != dossier_id:
        return AgentReuseOut(reused=False)
    fingerprint = await analysis_builder.agent_fingerprint(analyses, analysis, step)
    if fingerprint is None:
        return AgentReuseOut(reused=False)
    reused = await analysis_carryover.reuse_agent_unit(analyses, analysis, step, fingerprint)
    if reused is None:
        return AgentReuseOut(reused=False)
    return AgentReuseOut(reused=True, output=reused[1])


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


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut)
async def add_assistant_message(
    conversation_id: uuid.UUID,
    body: InternalMessageIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repository = DossierRepository(db)
    conversation = await repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable")
    conversation = await repository.add_message(
        conversation,
        MessageRole.ASSISTANT,
        body.content,
        sources=[s.model_dump() for s in body.sources],
    )
    message = conversation.messages[-1]
    message.feedback = None
    return message


@router.get("/conversations/{conversation_id}", response_model=InternalConversationOut)
async def get_internal_conversation(
    conversation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Conversation complète pour le worker : historique des messages +
    modèle LLM préféré. Le worker en a besoin pour construire le contexte
    du graphe LangGraph de chat."""
    conversation = await DossierRepository(db).get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable")
    return conversation


@router.post(
    "/conversations/{conversation_id}/chat-events",
    response_model=ChatEventOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_chat_event(
    conversation_id: uuid.UUID,
    body: ChatEventIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Dépose un événement de chat (tool_call, tool_result, thinking, done,
    error). Le worker appelle cette route pendant l'exécution du graphe
    LangGraph pour streamer la progression au frontend via SSE."""
    repository = DossierRepository(db)
    conversation = await repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable")
    return await repository.add_chat_event(conversation_id, body.kind, body.data)


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
    et d'extraction) pour le worker agent_execution. Réservé à l'API
    interne."""
    analyse = await AnalyseRepository(db).get(analyse_id)
    if analyse is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analyse introuvable")
    return InternalAnalyseOut(
        id=analyse.id,
        classification=InternalClassificationOut(
            prompt=analyse.classification_prompt,
            labels=[InternalLabelDefinitionOut.model_validate(label) for label in analyse.labels],
        ),
        extraction=InternalExtractionOut(
            prompt=analyse.extraction_prompt,
            entities=[InternalEntityDefinitionOut.model_validate(entity) for entity in analyse.entities],
        ),
        agents=[InternalAgentOut.model_validate(agent) for agent in analyse.agents],
    )


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


@router.get("/document-drafts/{draft_id}/context", response_model=InternalDraftContextOut)
async def get_draft_generation_context(draft_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    """Ce qu'il faut au worker pour générer : champs et états courants, éléments de la **révision figée** du
    brouillon, notes internes non archivées, métadonnées du dossier et prompt en vigueur."""
    repository = DocumentDraftRepository(db)
    draft = await _draft_or_404(db, draft_id)
    template_version = await repository.template_version(draft)
    current = await repository.current_versions(draft.id)
    dossier = await DossierRepository(db).get(draft.dossier_id)
    prompt_number, prompt = await generation_prompt.current(db)
    notes = await DossierNoteRepository(db).list(draft.dossier_id)

    def day(moment) -> str | None:
        return moment.date().isoformat() if moment else None

    return InternalDraftContextOut(
        draft_id=draft.id,
        dossier_id=draft.dossier_id,
        status=draft.status,
        requested_by=draft.generation_requested_by,
        template_name=template_version.name,
        generation_instructions=template_version.generation_instructions,
        fields=[
            InternalFieldOut(
                name=d.name,
                label=d.label,
                type=d.type,
                required=d.required,
                instruction=d.instruction,
                source=d.source.model_dump(),
                status=current[d.name].status,
                value=current[d.name].value,
                origin=current[d.name].origin,
            )
            for d in template_definitions(template_version)
        ],
        elements=[
            InternalElementOut(
                id=e.element.id,
                version_id=e.version.id,
                kind=e.element.kind,
                name=e.element.definition_name,
                text=e.text,
                page=e.element.first_page_number,
                document_id=e.element.document_id,
            )
            for e in await load_revision_elements(db, draft.revision_id)
        ],
        notes=[
            InternalDraftNoteOut(id=n.id, version_number=n.current.version_number, content=n.current.content)
            for n in notes
        ],
        metadata={
            "dossier_name": dossier.name if dossier else None,
            "dossier_created_at": day(dossier.created_at) if dossier else None,
            "dossier_started_at": day(dossier.started_at) if dossier else None,
            "dossier_ended_at": day(dossier.ended_at) if dossier else None,
        },
        prompt_version_number=prompt_number,
        prompt_label=generation_prompt.version_label(prompt_number),
        prompt=prompt,
    )


@router.post("/document-drafts/{draft_id}/fields/{name}/propose", response_model=FieldVersionOut)
async def propose_draft_field(
    draft_id: uuid.UUID, name: str, body: InternalProposeIn, db: Annotated[AsyncSession, Depends(get_db)]
):
    """Le worker dépose la proposition de l'agent pour un champ. **409** si le champ est validé : une valeur
    validée n'est jamais réécrite automatiquement ; **422** si la valeur ne correspond pas au type du champ."""
    repository = DocumentDraftRepository(db)
    draft = await _draft_or_404(db, draft_id)
    definition = next(
        (d for d in template_definitions(await repository.template_version(draft)) if d.name == name), None
    )
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Champ inconnu : {name}")
    try:
        return await repository.propose(
            draft,
            definition,
            body.value,
            sources=body.sources,
            prompt_version=body.prompt_version,
            model=body.model,
            instruction=body.instruction,
        )
    except ValidatedFieldError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except UnknownFieldError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (DraftError, FieldValueError) as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


@router.post("/document-drafts/{draft_id}/generation", status_code=status.HTTP_204_NO_CONTENT)
async def finish_draft_generation(
    draft_id: uuid.UUID, body: InternalGenerationIn, db: Annotated[AsyncSession, Depends(get_db)]
):
    """Le worker signale la fin de la génération (terminée ou en échec), avec les champs sans valeur trouvée."""
    draft = await _draft_or_404(db, draft_id)
    await DocumentDraftRepository(db).finish_generation(
        draft,
        status=body.status,
        proposal_count=body.proposal_count,
        missing=body.missing,
        truncated=body.truncated,
        prompt_version=body.prompt_version,
        error=body.error,
    )
