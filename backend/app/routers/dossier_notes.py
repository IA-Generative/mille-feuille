"""Routes des notes internes d'un dossier (issue #117, parent #106).

Réservées aux utilisateurs authentifiés : les notes sont **internes**, jamais
exposées côté usager (#96). Modifier ou restaurer ajoute une version ;
« supprimer » archive."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.dispatch import dispatch_note_proposals
from app.core.dossier_guard import require_dossier_visible
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.models.dossier_analysis import DossierAnalysisStatus
from app.models.dossier_note import DossierNote
from app.repositories.dossier_analysis_repository import DossierAnalysisRepository
from app.repositories.dossier_note_repository import (
    DossierNoteRepository,
    NoteAnalysisRunningError,
    NoteArchivedError,
    note_out,
)
from app.repositories.dossier_repository import DossierRepository
from app.schemas.dossier_note import NoteCreateIn, NoteOut, NoteRestoreIn, NoteUpdateIn, NoteVersionOut

router = APIRouter(
    prefix="/dossiers", tags=["Notes"], dependencies=[Depends(get_current_user), Depends(require_dossier_visible)]
)


async def _note_or_404(db: AsyncSession, dossier_id: uuid.UUID, note_id: uuid.UUID) -> DossierNote:
    if await DossierRepository(db).get(dossier_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")
    note = await DossierNoteRepository(db).get(dossier_id, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note introuvable")
    return note


@router.get("/{dossier_id}/notes", response_model=list[NoteOut])
async def list_notes(
    dossier_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    include_archived: Annotated[bool, Query()] = False,
):
    if await DossierRepository(db).get(dossier_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")
    notes = await DossierNoteRepository(db).list(dossier_id, include_archived=include_archived)
    return [note_out(note) for note in notes]


@router.post("/{dossier_id}/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(
    dossier_id: uuid.UUID,
    body: NoteCreateIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    if await DossierRepository(db).get(dossier_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")
    note = await DossierNoteRepository(db).create(dossier_id, content=body.content.strip(), user_id=user.user_id)
    return note_out(note)


@router.put("/{dossier_id}/notes/{note_id}", response_model=NoteOut)
async def update_note(
    dossier_id: uuid.UUID,
    note_id: uuid.UUID,
    body: NoteUpdateIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    """Modifier une note ajoute une version (l'ancienne reste dans l'historique)."""
    note = await _note_or_404(db, dossier_id, note_id)
    try:
        updated = await DossierNoteRepository(db).add_version(note, content=body.content.strip(), user_id=user.user_id)
    except NoteArchivedError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cette note est archivée") from error
    return note_out(updated)


@router.get("/{dossier_id}/notes/{note_id}/versions", response_model=list[NoteVersionOut])
async def list_note_versions(dossier_id: uuid.UUID, note_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    note = await _note_or_404(db, dossier_id, note_id)
    return note.versions


@router.post("/{dossier_id}/notes/{note_id}/restore", response_model=NoteOut)
async def restore_note_version(
    dossier_id: uuid.UUID,
    note_id: uuid.UUID,
    body: NoteRestoreIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    """Restaure une version antérieure : ajoute une version qui en reprend le contenu."""
    note = await _note_or_404(db, dossier_id, note_id)
    version = next((v for v in note.versions if v.id == body.version_id), None)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version introuvable pour cette note")
    try:
        updated = await DossierNoteRepository(db).add_version(
            note, content=version.content, user_id=user.user_id, restored_from=version.id
        )
    except NoteArchivedError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cette note est archivée") from error
    return note_out(updated)


@router.post("/{dossier_id}/notes/{note_id}/archive", response_model=NoteOut)
async def archive_note(dossier_id: uuid.UUID, note_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    """« Supprimer » une note l'archive : son historique est conservé."""
    note = await _note_or_404(db, dossier_id, note_id)
    return note_out(await DossierNoteRepository(db).set_archived(note, True))


@router.post("/{dossier_id}/notes/{note_id}/unarchive", response_model=NoteOut)
async def unarchive_note(dossier_id: uuid.UUID, note_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    note = await _note_or_404(db, dossier_id, note_id)
    return note_out(await DossierNoteRepository(db).set_archived(note, False))


@router.post("/{dossier_id}/notes/{note_id}/propose", response_model=NoteOut, status_code=status.HTTP_202_ACCEPTED)
async def propose_updates_from_note(
    dossier_id: uuid.UUID,
    note_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    """**Sur demande** : demande au worker d'analyser la note et de **proposer**
    des mises à jour de l'analyse de dossier. Ne se fait jamais seul : l'ajout ou
    la modification d'une note ne déclenche rien. Rien n'est appliqué, les
    propositions attendent la confirmation de l'utilisateur (#114). Le suivi est
    porté par la note (``analysis_status``)."""
    note = await _note_or_404(db, dossier_id, note_id)
    if note.archived:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cette note est archivée")
    analysis = await DossierAnalysisRepository(db).get_current(dossier_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aucune analyse pour ce dossier")
    if analysis.status == DossierAnalysisStatus.FIGEE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cette analyse est figée")
    try:
        started = await DossierNoteRepository(db).start_analysis(note, user_id=user.user_id)
    except NoteAnalysisRunningError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Cette note est déjà en cours d'analyse"
        ) from error
    dispatch_note_proposals(str(note.id))
    return note_out(started)
