import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_client import (
    dispatch_agent_execution,
    dispatch_analyse_suggestion,
    dispatch_chat_response,
    dispatch_classification,
    dispatch_document_summary,
    dispatch_dossier_summary,
    dispatch_entity_extraction,
    dispatch_text_extraction,
)
from app.connectors import s3_connector
from app.core.dossier_guard import require_dossier_visible
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.models.analyse import Analyse
from app.models.app_user import AppUser
from app.models.conversation import Message, MessageRole
from app.models.document_page import PredictionKind
from app.models.dossier import Dossier, DossierStatus, TextExtractionStatus
from app.models.dossier_access import Visibility
from app.models.dossier_event import DossierEventType
from app.repositories.analyse_repository import AnalyseRepository
from app.repositories.analysis_collaboration_repository import ElementLockedError
from app.repositories.dossier_access_repository import DossierAccessRepository
from app.repositories.dossier_event_repository import EventActor
from app.repositories.dossier_repository import DossierRepository
from app.repositories.user_directory_repository import UserDirectoryRepository
from app.schemas.dossier import (
    AssigneeUpdate,
    BulkAccessResult,
    BulkAccessUpdate,
    BulkAssigneeResult,
    BulkAssigneeUpdate,
    ChatEventOut,
    ConversationModelUpdate,
    ConversationOut,
    CustomValueIn,
    CustomValueOut,
    DocumentPageViewOut,
    DossierAccessChangeOut,
    DossierAccessOut,
    DossierAccessUpdate,
    DossierAssignIn,
    DossierCreate,
    DossierDocumentLabelIn,
    DossierDocumentOut,
    DossierGroupOut,
    DossierOut,
    DossierResultRowOut,
    DossierResultsBreakdownRowOut,
    DueAtUpdate,
    FeedbackIn,
    MessageIn,
    MessageOut,
    MessagePage,
    PredictionValidationIn,
    PredictionValidationOut,
    WorkflowStatusUpdate,
)
from app.schemas.pagination import Page
from app.services.custom_fields import normalize_value, validate_value
from app.services.prediction_validation import AnalysisFrozenError

router = APIRouter(
    prefix="/dossiers", tags=["Dossiers"], dependencies=[Depends(get_current_user), Depends(require_dossier_visible)]
)


async def _get_or_404(
    repository: DossierRepository, dossier_id: uuid.UUID, user: RequestContext | None = None
) -> Dossier:
    """Le dossier, ou 404. Avec ``user`` : 404 aussi s'il n'est pas visible de cette personne (issue #177), pour ne
    pas révéler l'existence d'un dossier restreint. Les routes qui n'ont pas encore ce filtre sont à brancher."""
    dossier = await repository.get(dossier_id, user)
    if dossier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")
    return dossier


@router.get("", response_model=Page[DossierOut])
async def list_dossiers(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    workflow_status_id: Annotated[
        uuid.UUID | None, Query(description="Ne garder que les dossiers de ce statut")
    ] = None,
    due: Annotated[
        Literal["overdue", "7", "30", "none"] | None,
        Query(
            description="Échéance, dossiers non clos : overdue (dépassée), 7 ou 30 (dans 7 / 30 jours ou moins), "
            "none (sans échéance)"
        ),
    ] = None,
    assignee: Annotated[
        str | None,
        Query(description="Responsable : me (moi), none (non affectés) ou l'identifiant d'une personne"),
    ] = None,
    sort: Annotated[
        Literal["created_at", "status", "due"],
        Query(
            description="created_at : plus récents d'abord ; status : par statut (ordre de l'analyse) ; "
            "due : échéance la plus proche d'abord"
        ),
    ] = "created_at",
) -> Page[DossierOut]:
    dossiers, total = await DossierRepository(db).list_paginated(
        page=page,
        page_size=page_size,
        workflow_status_id=workflow_status_id,
        due=due,
        assignee=user.user_id if assignee == "me" else assignee,
        sort=sort,
        user=user,
    )
    return Page.of(list(dossiers), total=total, page=page, page_size=page_size)


def _creation_access(body: DossierCreate, user: RequestContext) -> tuple[Visibility, list[str]]:
    """Accès d'un dossier créé par une personne (issue #177) : **restreint par défaut**, aux groupes qu'elle choisit
    parmi **les siens** (à défaut, tous les siens). Un dossier restreint a au moins un groupe : le créateur n'a
    aucun droit propre, il n'y accède que par eux."""
    visibility = Visibility(body.visibility or Visibility.RESTRICTED.value)
    mine = list(user.groups)
    paths = list(dict.fromkeys(body.group_paths if body.group_paths is not None else mine))
    # Un dossier « selon l'analyse » n'a pas de groupe : ceux qu'on enverrait sont ignorés.
    foreign = [p for p in paths if p not in mine] if visibility is Visibility.RESTRICTED else []
    if foreign:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "group_not_yours",
                "message": "On ne peut associer que ses propres groupes.",
                "groups": foreign,
            },
        )
    if visibility is Visibility.RESTRICTED and not paths:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "groups_required",
                "message": "Un dossier restreint a besoin d'au moins un groupe : choisissez-en un parmi les vôtres.",
            },
        )
    return visibility, paths if visibility is Visibility.RESTRICTED else []


async def create_dossier_for(
    body: DossierCreate,
    db: AsyncSession,
    actor: "RequestContext | EventActor | None" = None,
    visibility: Visibility = Visibility.ANALYSE,
    group_paths: list[str] | None = None,
) -> Dossier:
    """Crée un dossier et le journalise (#169). Partagé avec l'agent assistant (MCP) et la route interne, qui
    n'ont pas de session utilisateur : ``actor`` vaut alors l'identité du jeton, ou None, et le dossier est
    « selon l'analyse ». La route des utilisateurs passe l'accès décidé par `_creation_access`."""
    analyse: Analyse | None = None
    if body.analyse_id is not None:
        analyse = await AnalyseRepository(db).get(body.analyse_id)
        if analyse is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Analyse introuvable")

    dossier_repository = DossierRepository(db)
    dossier = await dossier_repository.create(
        name=body.name, analyse=analyse, actor=actor, visibility=visibility, group_paths=group_paths or ()
    )
    return await _get_or_404(dossier_repository, dossier.id)


@router.post("", response_model=DossierOut, status_code=status.HTTP_201_CREATED)
async def create_dossier(
    body: DossierCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> Dossier:
    visibility, group_paths = _creation_access(body, user)
    return await create_dossier_for(body, db, user, visibility, group_paths)


@router.put("/{dossier_id}/workflow-status", response_model=DossierOut)
async def update_workflow_status(
    dossier_id: uuid.UUID,
    body: WorkflowStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> Dossier:
    """Change le statut de dossier (issue #168). Refuse un statut qui n'appartient pas à l'analyse du
    dossier. Un statut final pose la date de clôture, tout autre l'efface."""
    repository = DossierRepository(db)
    dossier = await _get_or_404(repository, dossier_id)
    if dossier.analyse_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Dossier sans analyse : aucun statut n'est disponible."
        )
    analyse = await AnalyseRepository(db).get(dossier.analyse_id)
    new_status = next((s for s in analyse.statuses if s.id == body.status_id), None) if analyse else None
    if new_status is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Ce statut n'appartient pas à l'analyse du dossier."
        )
    await repository.set_workflow_status(dossier, new_status, actor=user)
    return await _get_or_404(repository, dossier_id)


async def _known_person(db: AsyncSession, person_id: str | None) -> AppUser | None:
    """La personne à affecter, dans l'annuaire local ; ``None`` pour désaffecter. Une personne inconnue (jamais
    connectée) ne peut pas recevoir de dossier : 422."""
    if person_id is None:
        return None
    person = await UserDirectoryRepository(db).get(person_id)
    if person is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "unknown_user", "message": "Cette personne n'est pas connue de l'application."},
        )
    return person


async def _require_access_for(db: AsyncSession, person: AppUser | None, dossiers: list[Dossier]) -> None:
    """On n'affecte qu'une personne qui a **déjà accès** au dossier (issue #177) ; tout ou rien, avec la liste des
    dossiers qu'elle ne peut pas voir. Son accès est celui de sa dernière connexion (annuaire)."""
    if person is None:
        return
    access = DossierAccessRepository(db)
    refused = [str(d.id) for d in dossiers if not await access.person_can_view(person, d)]
    if refused:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "assignee_has_no_access",
                "message": "Cette personne n'a pas accès à ce dossier.",
                "dossier_ids": refused,
            },
        )


# Les routes statiques (`bulk-assignee`) restent avant les routes `/{dossier_id}`.
@router.put("/bulk-assignee", response_model=BulkAssigneeResult)
async def assign_dossiers(
    body: BulkAssigneeUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> BulkAssigneeResult:
    """Affecte (ou désaffecte, avec ``assignee_id: null``) plusieurs dossiers **en une transaction** : si l'un
    d'eux n'existe pas, aucun n'est modifié (404, avec la liste des identifiants introuvables)."""
    repository = DossierRepository(db)
    person = await _known_person(db, body.assignee_id)
    wanted = list(dict.fromkeys(body.dossier_ids))
    dossiers = await repository.get_many(wanted, user)
    missing = sorted(str(i) for i in set(wanted) - {d.id for d in dossiers})
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "dossiers_not_found", "message": "Dossiers introuvables.", "dossier_ids": missing},
        )
    await _require_access_for(db, person, dossiers)
    updated = await repository.assign_many(dossiers, person, actor=user)
    return BulkAssigneeResult(updated=updated, unchanged=len(dossiers) - updated)


@router.put("/{dossier_id}/assignee", response_model=DossierOut)
async def update_assignee(
    dossier_id: uuid.UUID,
    body: AssigneeUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> Dossier:
    """Affecte le dossier à une personne de l'annuaire ; ``null`` le désaffecte. Le changement est tracé dans le
    journal (#169)."""
    repository = DossierRepository(db)
    dossier = await _get_or_404(repository, dossier_id, user)
    person = await _known_person(db, body.assignee_id)
    await _require_access_for(db, person, [dossier])
    await repository.set_assignee(dossier, person, actor=user)
    return await _get_or_404(repository, dossier_id, user)


def _access_out(
    dossier: Dossier,
    groups: list,
    user: RequestContext,
    assignee_unassigned: bool | None = None,
    unassigned_person: dict | None = None,
) -> DossierAccessChangeOut:
    return DossierAccessChangeOut(
        visibility=dossier.visibility,
        groups=[DossierGroupOut.model_validate(g) for g in groups],
        can_edit=user.is_admin,
        available_groups=sorted(user.groups),
        assignee_unassigned=bool(assignee_unassigned),
        unassigned_person=unassigned_person,
    )


@router.get("/{dossier_id}/access", response_model=DossierAccessOut)
async def get_dossier_access(
    dossier_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> DossierAccessChangeOut:
    """Visibilité et groupes du dossier. Lisible par ceux qui voient le dossier (404 sinon)."""
    dossier = await _get_or_404(DossierRepository(db), dossier_id, user)
    return _access_out(dossier, list(await DossierAccessRepository(db).groups_of(dossier_id)), user)


async def _checked_access_change(
    access: DossierAccessRepository, dossier_id: uuid.UUID, body: DossierAccessUpdate, user: RequestContext
) -> tuple[Visibility, list[str]]:
    """Valide un changement d'accès : seuls les administrateurs (403), un groupe **ajouté** doit être l'un des groupes
    de la personne (422), un dossier restreint garde au moins un groupe (422)."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Seuls les administrateurs modifient l'accès d'un dossier."
        )
    visibility = Visibility(body.visibility)
    wanted = list(dict.fromkeys(body.group_paths))
    current = set(await access.group_paths(dossier_id))
    foreign = [p for p in wanted if p not in current and p not in user.groups]
    if foreign:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "group_not_yours",
                "message": "On ne peut associer que ses propres groupes.",
                "groups": foreign,
            },
        )
    if visibility is Visibility.RESTRICTED and not wanted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "groups_required", "message": "Un dossier restreint a besoin d'au moins un groupe."},
        )
    return visibility, wanted


@router.put("/bulk-access", response_model=BulkAccessResult)
async def update_access_in_bulk(
    body: BulkAccessUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> BulkAccessResult:
    """Change l'accès de plusieurs dossiers **en une transaction** (administrateurs) : les groupes **remplacent** ceux
    de chaque dossier. Tout ou rien : un dossier introuvable (ou invisible) donne 404 avec la liste, un groupe qui
    n'est pas le sien 422. Les personnes affectées qui perdent l'accès sont désaffectées (tracé par dossier)."""
    repository = DossierRepository(db)
    access = DossierAccessRepository(db)
    wanted_ids = list(dict.fromkeys(body.dossier_ids))
    dossiers = await repository.get_many(wanted_ids, user)
    missing = sorted(str(i) for i in set(wanted_ids) - {d.id for d in dossiers})
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "dossiers_not_found", "message": "Dossiers introuvables.", "dossier_ids": missing},
        )
    updated = unassigned = 0
    try:
        for dossier in dossiers:
            visibility, wanted = await _checked_access_change(access, dossier.id, body, user)
            change = await access.update(
                dossier, visibility=visibility, group_paths=wanted, actor=user, granted_by=user.user_id, commit=False
            )
            updated += bool(change)
            unassigned += bool(change.get("assignee_unassigned"))
    except HTTPException:
        await db.rollback()
        raise
    await db.commit()
    return BulkAccessResult(updated=updated, unchanged=len(dossiers) - updated, unassigned=unassigned)


@router.put("/{dossier_id}/access", response_model=DossierAccessChangeOut)
async def update_dossier_access(
    dossier_id: uuid.UUID,
    body: DossierAccessUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    dry_run: Annotated[
        bool, Query(description="Simule : dit qui perdrait l'accès, sans rien enregistrer ni tracer")
    ] = False,
) -> DossierAccessChangeOut:
    """Change la visibilité et les groupes du dossier. **Réservé aux administrateurs** (le créateur n'a aucun droit
    propre) ; un groupe ajouté doit faire partie des groupes de la personne qui modifie ; un dossier restreint garde
    au moins un groupe. Une personne affectée qui perd ainsi l'accès est désaffectée (tracé dans le journal).
    Avec ``dry_run``, rien n'est enregistré : la réponse nomme la personne qui perdrait l'accès (pour la confirmer)."""
    dossier = await _get_or_404(DossierRepository(db), dossier_id, user)
    access = DossierAccessRepository(db)
    visibility, wanted = await _checked_access_change(access, dossier_id, body, user)
    change = await access.update(
        dossier, visibility=visibility, group_paths=wanted, actor=user, granted_by=user.user_id, commit=not dry_run
    )
    if dry_run:
        await db.rollback()
    refreshed = await _get_or_404(DossierRepository(db), dossier_id, user)
    return _access_out(
        refreshed,
        list(await access.groups_of(dossier_id)),
        user,
        change.get("assignee_unassigned"),
        change.get("unassigned_person"),
    )


@router.put("/{dossier_id}/custom-values/{field_id}", response_model=CustomValueOut)
async def put_custom_value(
    dossier_id: uuid.UUID,
    field_id: str,
    body: CustomValueIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> CustomValueOut:
    """Pose la valeur d'une colonne personnalisée du suivi (issue #173). Elle est **validée selon le type** du champ
    (422 avec le message à afficher dans la cellule) et tracée dans le journal : ancienne et nouvelle valeur, auteur.
    ``null`` ou une chaîne vide l'efface, sauf si le champ est obligatoire."""
    repository = DossierRepository(db)
    dossier = await _get_or_404(repository, dossier_id, user)
    analyse = await AnalyseRepository(db).get(dossier.analyse_id) if dossier.analyse_id else None
    field = next((f for f in (analyse.custom_fields if analyse else []) if f["id"] == field_id), None)
    if field is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Colonne introuvable pour ce dossier")
    error = validate_value(field, body.value)
    if error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": "invalid_value", "message": error}
        )
    value = normalize_value(body.value)
    await repository.set_custom_value(dossier, field, value, actor=user)
    return CustomValueOut(field_id=field_id, value=value)


@router.put("/{dossier_id}/due-at", response_model=DossierOut)
async def update_due_at(
    dossier_id: uuid.UUID,
    body: DueAtUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> Dossier:
    """Change la date d'échéance du dossier (``null`` la supprime). Le changement est tracé dans le journal (#169) ;
    le niveau d'échéance (``due``) est recalculé par le serveur selon les seuils de l'analyse."""
    repository = DossierRepository(db)
    dossier = await _get_or_404(repository, dossier_id)
    await repository.set_due_at(dossier, body.due_at, actor=user)
    return await _get_or_404(repository, dossier_id)


@router.get("/{dossier_id}", response_model=DossierOut)
async def get_dossier(
    request: Request,
    dossier_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> Dossier:
    repository = DossierRepository(db)
    dossier = await _get_or_404(repository, dossier_id, user)
    # Consultation tracée dans le journal (#169), une fois par utilisateur dans la fenêtre de dédoublonnage. Un
    # administrateur qui entre sans être membre est déjà tracé à part (accès administrateur, #182) : sa
    # consultation ne s'affiche pas en plus parmi celles des membres.
    if not getattr(request.state, "admin_only", False):
        await repository.events.record_consultation(dossier_id, user)
    return dossier


@router.post("/{dossier_id}/documents", response_model=DossierOut)
async def add_documents(
    dossier_id: uuid.UUID,
    files: list[UploadFile],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> Dossier:
    repository = DossierRepository(db)
    dossier = await _get_or_404(repository, dossier_id)
    documents = []
    for f in files:
        data = await f.read()
        s3_key = f"dossiers/{dossier_id}/{uuid.uuid4()}-{f.filename or 'document'}"
        mimetype = f.content_type or "application/octet-stream"
        # boto3 est synchrone : hors du threadpool, cet appel bloquerait la
        # boucle asyncio le temps de l'upload.
        await run_in_threadpool(s3_connector.upload, s3_key, data, mimetype)
        documents.append(
            {
                "name": f.filename or "document",
                "size": len(data),
                "s3_key": s3_key,
                "mimetype": mimetype,
            }
        )
    created = await repository.add_documents(dossier, documents)
    for document in created:
        dispatch_text_extraction(str(document.id))
        # Ni le nom ni le contenu du fichier : ce sont des données d'usager (#169).
        repository.events.add(
            dossier_id,
            DossierEventType.DOCUMENT_ADDED,
            user,
            {"document_id": str(document.id), "mimetype": document.mimetype, "size": document.size},
        )
    await db.commit()
    # Pas `return dossier` : refresh(dossier) (dans add_documents) réexpire
    # `documents`, dont les nouveaux DossierDocument n'ont pas `pages` chargée
    # (MissingGreenlet à la sérialisation) - une requête fraîche via
    # _get_or_404 a le eager loading complet de _base_query.
    return await _get_or_404(repository, dossier_id)


@router.put("/{dossier_id}/documents/{document_id}/label", response_model=DossierDocumentOut)
async def set_document_label(
    dossier_id: uuid.UUID,
    document_id: uuid.UUID,
    body: DossierDocumentLabelIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    repository = DossierRepository(db)
    document = await repository.get_document(dossier_id, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable")
    await repository.set_document_label(document, body.label)
    return document


@router.get("/{dossier_id}/documents/{document_id}/pages/{page_id}", response_model=DocumentPageViewOut)
async def get_document_page(
    dossier_id: uuid.UUID,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentPageViewOut:
    """Page d'un document (texte extrait, zones, présence d'une capture) :
    alimente la modale « source » ouverte depuis une réponse du chat."""
    repository = DossierRepository(db)
    document = await repository.get_document(dossier_id, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable")
    page = await repository.get_page(document_id, page_id)
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page introuvable")
    return DocumentPageViewOut(
        id=page.id,
        page_number=page.page_number,
        width=page.width,
        height=page.height,
        content=page.content,
        has_screenshot=page.has_screenshot,
        bounding_boxes=page.bounding_boxes,
        document_id=document.id,
        document_name=document.name,
    )


@router.get("/{dossier_id}/documents/{document_id}/pages/{page_id}/screenshot")
async def get_page_screenshot(
    dossier_id: uuid.UUID,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Relaie la capture d'une page depuis S3 - jamais d'URL S3 signée
    renvoyée au frontend : seule cette route (protégée par la session
    Keycloak, comme tout /api/dossiers/*) a les identifiants du bucket."""
    repository = DossierRepository(db)
    document = await repository.get_document(dossier_id, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable")
    page = await repository.get_page(document_id, page_id)
    if page is None or page.screenshot_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capture introuvable")
    data, content_type = await run_in_threadpool(s3_connector.download, page.screenshot_key)
    return Response(content=data, media_type=content_type)


async def launch_dossier_for(
    dossier_id: uuid.UUID, db: AsyncSession, actor: "RequestContext | EventActor | None" = None
) -> Dossier:
    """Lance l'analyse d'un dossier et le journalise (#169) ; partagé avec l'agent assistant."""
    dossier_repository = DossierRepository(db)
    dossier = await _get_or_404(dossier_repository, dossier_id, actor if isinstance(actor, RequestContext) else None)
    analyse = await AnalyseRepository(db).get(dossier.analyse_id)
    if analyse is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Analyse introuvable")
    await dossier_repository.launch(dossier, analyse, actor=actor)
    # Dépose les tâches de classification et d'extraction sur la file
    # agent_execution : le worker traite chaque page (VLM + LLM) et dépose
    # les prédictions via l'API interne. Les tâches sont indépendantes et
    # tournent en parallèle sur la file dédiée.
    dispatch_classification(str(dossier.id))
    dispatch_entity_extraction(str(dossier.id))
    # L'exécution des agents est déposée séparément : elle attend que la
    # classification et l'extraction soient terminées avant de lancer les
    # agents LangGraph (les agents utilisent les prédictions déposées).
    dispatch_agent_execution(str(dossier.id))
    return dossier


@router.post("/{dossier_id}/launch", response_model=DossierOut)
async def launch_dossier(
    dossier_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> Dossier:
    return await launch_dossier_for(dossier_id, db, user)


@router.post("/{dossier_id}/stop", response_model=DossierOut)
async def stop_dossier(
    dossier_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> Dossier:
    repository = DossierRepository(db)
    dossier = await _get_or_404(repository, dossier_id)
    await repository.stop(dossier, actor=user)
    return dossier


@router.post("/{dossier_id}/documents/{document_id}/summary", response_model=DossierDocumentOut)
async def regenerate_document_summary(
    dossier_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Déclenche la (re)génération du résumé d'un document via le worker
    agent_execution. Le worker concatène le contenu des pages, appelle le
    LLM, et dépose le résumé via l'API interne."""
    repository = DossierRepository(db)
    document = await repository.get_document(dossier_id, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable")
    dispatch_document_summary(str(dossier_id), str(document_id))
    return document


@router.post("/{dossier_id}/summary", response_model=DossierOut)
async def regenerate_dossier_summary(
    dossier_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Déclenche la (re)génération du résumé global du dossier via le worker
    agent_execution. Le worker récupère les résumés individuels des documents
    + les synthèses des agents, et produit une vue d'ensemble."""
    repository = DossierRepository(db)
    dossier = await _get_or_404(repository, dossier_id)
    dispatch_dossier_summary(str(dossier_id))
    return dossier


@router.post("/{dossier_id}/suggest-analysis", response_model=DossierOut)
async def suggest_analysis(
    dossier_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Déclenche la (re)génération des suggestions d'analyse pour un dossier
    « à ranger » (issue #54). Le worker récupère les résumés des documents +
    la liste des analyses disponibles, appelle le LLM, et dépose les
    suggestions via l'API interne."""
    repository = DossierRepository(db)
    dossier = await _get_or_404(repository, dossier_id)
    dispatch_analyse_suggestion(str(dossier.id))
    return dossier


@router.post("/{dossier_id}/assign", response_model=DossierOut)
async def assign_dossier(
    dossier_id: uuid.UUID,
    body: DossierAssignIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    """Valide le rattachement d'un dossier « à ranger » à une analyse
    (issue #54). L'utilisateur peut valider une suggestion ou choisir
    manuellement une autre analyse."""
    repository = DossierRepository(db)
    dossier = await _get_or_404(repository, dossier_id)
    analyse = await AnalyseRepository(db).get(body.analyse_id)
    if analyse is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Analyse introuvable")
    await repository.assign_analyse(dossier, analyse, actor=user)
    return await _get_or_404(repository, dossier_id)


@router.get("/{dossier_id}/results/breakdown", response_model=list[DossierResultsBreakdownRowOut])
async def get_results_breakdown(
    dossier_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> list[dict]:
    """Répartition par fichier des pages classifiées et des entités extraites (cartes Classification / Entités)."""
    repository = DossierRepository(db)
    await _get_or_404(repository, dossier_id, user)
    return await repository.results_breakdown(dossier_id)


@router.get("/{dossier_id}/results", response_model=Page[DossierResultRowOut])
async def list_results(
    dossier_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    kind: Annotated[PredictionKind, Query(description="label : classifications, entity : entités")],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
) -> Page[DossierResultRowOut]:
    """Détail paginé des classifications ou des entités d'un dossier, avec fichier et pages."""
    repository = DossierRepository(db)
    await _get_or_404(repository, dossier_id, user)
    predictions, total = await repository.list_predictions_paginated(
        dossier_id=dossier_id, kind=kind, page=page, page_size=page_size
    )
    rows = []
    for prediction in predictions:
        document = prediction.pages[0].document
        pages = [p for p in prediction.pages if p.document.id == document.id]
        page_ids = {p.id for p in pages}
        rows.append(
            DossierResultRowOut(
                id=prediction.id,
                name=prediction.name,
                value=prediction.value,
                confidence=prediction.confidence,
                document_id=document.id,
                document_name=document.name,
                pages=pages,
                bounding_boxes=[b for b in prediction.bounding_boxes if b.document_page_id in page_ids],
            )
        )
    return Page.of(rows, total=total, page=page, page_size=page_size)


@router.get("/{dossier_id}/conversations", response_model=Page[ConversationOut])
async def list_conversations(
    dossier_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ConversationOut]:
    repository = DossierRepository(db)
    await _get_or_404(repository, dossier_id)
    conversations, total = await repository.list_conversations_paginated(
        dossier_id=dossier_id, user_id=user.user_id, page=page, page_size=page_size
    )
    return Page.of(list(conversations), total=total, page=page, page_size=page_size)


@router.post(
    "/{dossier_id}/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    dossier_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    repository = DossierRepository(db)
    await _get_or_404(repository, dossier_id)
    return await repository.create_conversation(dossier_id, user.user_id)


@router.delete(
    "/{dossier_id}/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    dossier_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    repository = DossierRepository(db)
    await _get_or_404(repository, dossier_id)
    conversation = await repository.get_conversation(conversation_id)
    if conversation is None or conversation.dossier_id != dossier_id or conversation.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable")
    await repository.delete_conversation(conversation)


@router.put(
    "/{dossier_id}/conversations/{conversation_id}/model",
    response_model=ConversationOut,
)
async def update_conversation_model(
    dossier_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: ConversationModelUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    repository = DossierRepository(db)
    await _get_or_404(repository, dossier_id)
    conversation = await repository.get_conversation(conversation_id)
    if conversation is None or conversation.dossier_id != dossier_id or conversation.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable")
    return await repository.update_conversation_model(conversation, body.model)


@router.get(
    "/{dossier_id}/conversations/{conversation_id}/messages",
    response_model=MessagePage,
)
async def list_messages(
    dossier_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before: Annotated[uuid.UUID | None, Query(description="Id du message le plus ancien déjà chargé")] = None,
) -> MessagePage:
    """Messages d'une conversation par page (curseur), du plus récent au plus
    ancien : sans `before`, les `limit` derniers messages ; avec `before`,
    les `limit` messages qui le précèdent. `items` est en ordre chronologique."""
    repository = DossierRepository(db)
    await _get_or_404(repository, dossier_id)
    conversation = await repository.get_conversation(conversation_id)
    if conversation is None or conversation.dossier_id != dossier_id or conversation.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable")
    messages, has_more = await repository.list_messages_page(conversation_id, limit=limit, before_id=before)
    return MessagePage(items=[_with_feedback(m, user.user_id) for m in messages], has_more=has_more)


@router.post(
    "/{dossier_id}/conversations/{conversation_id}/messages",
    response_model=MessageOut,
)
async def add_message(
    dossier_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: MessageIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    repository = DossierRepository(db)
    await _get_or_404(repository, dossier_id)
    conversation = await repository.get_conversation(conversation_id)
    if conversation is None or conversation.dossier_id != dossier_id or conversation.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable")
    # Nettoie les événements de chat de l'exécution précédente : le
    # frontend SSE ne doit voir que les événements de cette nouvelle
    # exécution, pas ceux d'un run précédent.
    await repository.delete_chat_events(conversation_id)
    conversation = await repository.add_message(conversation, MessageRole.USER, body.content)
    # Déclenche la tâche Celery de réponse au chat : le worker charge
    # l'historique + les synthèses, exécute le graphe LangGraph, dépose
    # les événements intermédiaires (chat_events) et le message assistant
    # final (avec sources) via l'API interne.
    dispatch_chat_response(str(conversation_id), str(dossier_id))
    return _with_feedback(conversation.messages[-1], user.user_id)


def _with_feedback(message: Message, user_id: str) -> Message:
    """Ne garde que le feedback de l'utilisateur courant (MessageOut.feedback)."""
    message.feedback = next((f for f in message.feedbacks if f.user_id == user_id), None)
    return message


@router.put(
    "/{dossier_id}/conversations/{conversation_id}/messages/{message_id}/feedback",
    response_model=MessageOut,
)
async def set_message_feedback(
    dossier_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    body: FeedbackIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    repository = DossierRepository(db)
    await _get_or_404(repository, dossier_id)
    conversation = await repository.get_conversation(conversation_id)
    if conversation is None or conversation.dossier_id != dossier_id or conversation.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable")
    message = next((m for m in conversation.messages if m.id == message_id), None)
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message introuvable")
    conversation = await repository.set_feedback(message, user.user_id, body.value, body.reasons, body.comment)
    return _with_feedback(next(m for m in conversation.messages if m.id == message_id), user.user_id)


@router.delete(
    "/{dossier_id}/conversations/{conversation_id}/messages/{message_id}/feedback",
    response_model=MessageOut,
)
async def delete_message_feedback(
    dossier_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    repository = DossierRepository(db)
    await _get_or_404(repository, dossier_id)
    conversation = await repository.get_conversation(conversation_id)
    if conversation is None or conversation.dossier_id != dossier_id or conversation.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable")
    message = next((m for m in conversation.messages if m.id == message_id), None)
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message introuvable")
    conversation = await repository.delete_feedback(message, user.user_id)
    return _with_feedback(next(m for m in conversation.messages if m.id == message_id), user.user_id)


@router.put(
    "/{dossier_id}/documents/{document_id}/pages/{page_id}/predictions/{prediction_id}/validations",
    response_model=PredictionValidationOut,
)
async def validate_prediction(
    dossier_id: uuid.UUID,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
    prediction_id: uuid.UUID,
    body: PredictionValidationIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    repository = DossierRepository(db)
    document = await repository.get_document(dossier_id, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable")
    page = await repository.get_page(document_id, page_id)
    prediction = await repository.get_prediction(page_id, prediction_id) if page else None
    if page is None or prediction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prédiction introuvable")
    try:
        updated = await repository.add_prediction_validation(
            prediction,
            page,
            validator_user_id=user.user_id,
            status=body.status,
            corrected_value=body.corrected_value,
            bounding_box=body.bounding_box.model_dump() if body.bounding_box else None,
        )
    except AnalysisFrozenError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cette analyse est figée") from error
    except ElementLockedError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error.message) from error
    return updated.validations[-1]


_TERMINAL_STATUSES = {DossierStatus.TERMINE, DossierStatus.ARRETE, DossierStatus.ECHEC}
_EXTRACTION_IN_PROGRESS = {
    TextExtractionStatus.EN_ATTENTE,
    TextExtractionStatus.EN_COURS,
}


def _has_active_work(dossier: Dossier) -> bool:
    """True tant qu'il y a du travail en cours : le dossier est lancé
    (classification/extraction/agents) ou au moins un document est en cours
    d'extraction de texte (qui démarre dès l'upload, avant tout lancement)."""
    if dossier.status == DossierStatus.EN_COURS:
        return True
    return any(doc.text_extraction_status in _EXTRACTION_IN_PROGRESS for doc in dossier.documents)


async def _execution_events(repository: DossierRepository, dossier_id: uuid.UUID) -> AsyncIterator[str]:
    """Un événement SSE par changement d'état, jusqu'à ce qu'il n'y ait plus
    de travail actif (dossier terminal ou extraction de texte terminée) -
    pas de bus de messages (Redis pub/sub, etc), juste un polling DB léger :
    suffisant pour un état affiché dans l'UI, pas conçu pour du temps réel à
    grande échelle."""
    last_payload: str | None = None
    while True:
        dossier = await repository.get(dossier_id)
        if dossier is None:
            yield 'event: error\ndata: {"detail": "Dossier introuvable"}\n\n'
            return
        payload = json.dumps(DossierOut.model_validate(dossier).model_dump(mode="json"))
        if payload != last_payload:
            yield f"event: execution-update\ndata: {payload}\n\n"
            last_payload = payload
        if dossier.status in _TERMINAL_STATUSES or not _has_active_work(dossier):
            yield "event: done\ndata: {}\n\n"
            return
        await asyncio.sleep(1)


@router.get("/{dossier_id}/stream")
async def stream_dossier_execution(dossier_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    repository = DossierRepository(db)
    await _get_or_404(repository, dossier_id)
    return StreamingResponse(
        _execution_events(repository, dossier_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- SSE : streaming des événements de chat ---
#
# Le frontend s'abonne à ce flux après avoir envoyé un message utilisateur.
# Le worker dépose des chat_events (tool_call, tool_result, thinking, done,
# error) en base pendant l'exécution du graphe LangGraph ; ce flux les
# relaie au navigateur via SSE, en pollant la base (même pattern que
# _execution_events pour le streaming d'exécution de dossier).


async def _chat_events(
    repository: DossierRepository,
    conversation_id: uuid.UUID,
    user_id: str,
) -> AsyncIterator[str]:
    """Émet les événements de chat via SSE, jusqu'à recevoir l'événement
    `done` ou `error` qui marque la fin de l'exécution. Polling DB léger
    (500ms) : suffisant pour une UI réactive sans infrastructure de
    pub/sub."""
    last_seen_id: uuid.UUID | None = None
    while True:
        # Vérifie que la conversation appartient toujours à l'utilisateur
        # (sécurité : le SSE est authentifié mais on vérifie à chaque poll).
        conversation = await repository.get_conversation(conversation_id)
        if conversation is None or conversation.user_id != user_id:
            yield 'event: error\ndata: {"detail": "Conversation introuvable"}\n\n'
            return

        events = await repository.list_chat_events(conversation_id, after_id=last_seen_id)
        for event in events:
            last_seen_id = event.id
            payload = ChatEventOut.model_validate(event).model_dump(mode="json")
            data = json.dumps(payload)
            yield f"event: chat-event\ndata: {data}\n\n"
            # L'événement `done` ou `error` marque la fin du flux : on
            # émet un événement SSE `done` explicite pour que le frontend
            # (addEventListener('done', ...)) le capte avant la fermeture.
            if event.kind in ("done", "error"):
                yield "event: done\ndata: {}\n\n"
                return
        await asyncio.sleep(0.5)


@router.get(
    "/{dossier_id}/conversations/{conversation_id}/stream",
)
async def stream_chat_events(
    dossier_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    """Flux SSE des événements de chat : le frontend s'y abonne après avoir
    envoyé un message utilisateur pour suivre l'exécution du graphe LangGraph
    en temps réel (appels d'outils, résultats, étapes intermédiaires)."""
    repository = DossierRepository(db)
    await _get_or_404(repository, dossier_id)
    conversation = await repository.get_conversation(conversation_id)
    if conversation is None or conversation.dossier_id != dossier_id or conversation.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable")
    return StreamingResponse(
        _chat_events(repository, conversation_id, user.user_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
