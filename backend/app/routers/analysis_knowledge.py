import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.models.analyse import Analyse
from app.repositories.analyse_repository import AnalyseRepository
from app.routers.knowledge_sources import get_knowledge_client
from app.routers.tool_servers import get_identity_tokens
from app.schemas.analyse import Version
from app.schemas.knowledge_collection import (
    KnowledgeCollectionsOut,
    KnowledgeCollectionsUpdate,
    StoredKnowledgeCollection,
)
from app.services.knowledge.analyse_collections import (
    CollectionsRefusedError,
    describe_collections,
    validate_collections,
)
from app.services.knowledge.client import KnowledgeClient
from app.services.tools.identity_tokens import IdentityTokens

router = APIRouter(prefix="/analyses", tags=["Knowledge"], dependencies=[Depends(get_current_user)])


async def _analyse_or_404(repository: AnalyseRepository, analyse_id: uuid.UUID) -> Analyse:
    analyse = await repository.get(analyse_id)
    if analyse is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analyse introuvable")
    return analyse


async def _out(
    repository: AnalyseRepository,
    analyse: Analyse,
    db: AsyncSession,
    user: RequestContext,
    client: KnowledgeClient,
    identity_tokens: IdentityTokens,
) -> KnowledgeCollectionsOut:
    from app.models.analyse import VersionedField

    return KnowledgeCollectionsOut(
        collections=await describe_collections(db, user, client, identity_tokens, analyse.knowledge_collections),
        versions=[
            Version(
                id=v.id,
                content=[StoredKnowledgeCollection.model_validate(item) for item in v.content],
                created_at=v.created_at,
            )
            for v in repository.field_versions(analyse, VersionedField.KNOWLEDGE_COLLECTIONS)
        ],
    )


@router.get("/{analyse_id}/knowledge-collections", response_model=KnowledgeCollectionsOut)
async def get_knowledge_collections(
    analyse_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    client: Annotated[KnowledgeClient, Depends(get_knowledge_client)],
    identity_tokens: Annotated[IdentityTokens, Depends(get_identity_tokens)],
) -> KnowledgeCollectionsOut:
    """Les collections autorisées pour l'analyse, avec leur état **pour la personne qui demande** (disponible,
    introuvable, accès refusé, source inaccessible) et le nom à jour, plus l'historique des listes précédentes."""
    repository = AnalyseRepository(db)
    analyse = await _analyse_or_404(repository, analyse_id)
    return await _out(repository, analyse, db, user, client, identity_tokens)


@router.put("/{analyse_id}/knowledge-collections", response_model=KnowledgeCollectionsOut)
async def update_knowledge_collections(
    analyse_id: uuid.UUID,
    body: KnowledgeCollectionsUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    client: Annotated[KnowledgeClient, Depends(get_knowledge_client)],
    identity_tokens: Annotated[IdentityTokens, Depends(get_identity_tokens)],
) -> KnowledgeCollectionsOut:
    """Remplace la liste. Seules les collections **ajoutées** sont contrôlées (source visible, collection retrouvée
    chez le fournisseur avec les droits de la personne) ; le nom enregistré est celui du fournisseur. L'état précédent
    est conservé dans l'historique."""
    repository = AnalyseRepository(db)
    analyse = await _analyse_or_404(repository, analyse_id)
    try:
        collections = await validate_collections(
            db, user, client, identity_tokens, body.collections, already=analyse.knowledge_collections
        )
    except CollectionsRefusedError as error:
        detail = {
            "code": "collections_refusees",
            "message": error.message,
            "collections": [
                {"source_id": str(r.source_id), "collection_id": r.collection_id, "reason": r.reason}
                for r in error.refused
            ],
        }
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail) from error
    await repository.update_knowledge_collections(analyse, collections)
    return await _out(repository, analyse, db, user, client, identity_tokens)


@router.post("/{analyse_id}/knowledge-collections/restore/{version_id}", response_model=KnowledgeCollectionsOut)
async def restore_knowledge_collections(
    analyse_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    client: Annotated[KnowledgeClient, Depends(get_knowledge_client)],
    identity_tokens: Annotated[IdentityTokens, Depends(get_identity_tokens)],
) -> KnowledgeCollectionsOut:
    """Restaure une liste antérieure telle qu'elle était ; la liste courante devient elle-même une version. Une
    collection devenue inaccessible depuis est signalée, pas refusée."""
    repository = AnalyseRepository(db)
    analyse = await _analyse_or_404(repository, analyse_id)
    version = repository.knowledge_collections_version(analyse, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Version introuvable")
    await repository.update_knowledge_collections(analyse, list(version.content))
    return await _out(repository, analyse, db, user, client, identity_tokens)
