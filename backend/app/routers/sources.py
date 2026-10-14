import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dossier_guard import check_dossier_access
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.models.document_source import DocumentSource
from app.repositories.document_source_repository import DocumentSourceRepository, SourceNameTakenError
from app.schemas.document_source import DocumentSourceIn, DocumentSourceOut

router = APIRouter(prefix="/sources", tags=["Sources"])


async def _get_writable_or_404(
    db: AsyncSession, repository: DocumentSourceRepository, source_id: uuid.UUID, user: RequestContext
) -> DocumentSource:
    """La source, ou 404. Une source tampon appartient à un dossier : elle suit sa visibilité (404 si la personne ne
    voit pas le dossier). Une source de catalogue suit les règles des analyses (tout compte connecté)."""
    source = await repository.get(source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source introuvable")
    if source.dossier_id is not None:
        await check_dossier_access(db, source.dossier_id, user, method="PUT", write=True)
    return source


@router.put("/{source_id}", response_model=DocumentSourceOut)
async def update_source(
    source_id: uuid.UUID,
    body: DocumentSourceIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    repository = DocumentSourceRepository(db)
    source = await _get_writable_or_404(db, repository, source_id, user)
    try:
        return await repository.update(source, name=body.name, description=body.description)
    except SourceNameTakenError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Une source porte déjà ce nom") from error


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> Response:
    """Supprime une source, même utilisée : ses documents restent, sans source."""
    repository = DocumentSourceRepository(db)
    source = await _get_writable_or_404(db, repository, source_id, user)
    await repository.delete(source)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
