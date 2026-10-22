from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.acting_user import acting_user
from app.core.security.factory import RequestContext
from app.core.security.internal import verify_app_token
from app.db import get_db
from app.repositories.analyse_repository import AnalyseRepository
from app.routers.internal_tools import get_call_limiter
from app.routers.knowledge_sources import get_knowledge_client
from app.routers.tool_servers import get_identity_tokens
from app.schemas.knowledge_search import KnowledgeSearchIn, KnowledgeSearchOut
from app.services.knowledge.client import KnowledgeClient
from app.services.knowledge.search_service import KnowledgeSearchService
from app.services.tools.call_limits import CallLimiter
from app.services.tools.identity_tokens import IdentityTokens

router = APIRouter(
    prefix="/internal/knowledge", tags=["Internal", "Knowledge"], dependencies=[Depends(verify_app_token)]
)


@router.post("/search", response_model=KnowledgeSearchOut)
async def search_knowledge_base(
    body: KnowledgeSearchIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(acting_user)],
    client: Annotated[KnowledgeClient, Depends(get_knowledge_client)],
    identity_tokens: Annotated[IdentityTokens, Depends(get_identity_tokens)],
    limiter: Annotated[CallLimiter, Depends(get_call_limiter)],
    x_acting_user: Annotated[str | None, Header()] = None,
) -> KnowledgeSearchOut:
    """Cherche dans les collections que l'analyse autorise, au nom de la personne transmise (`X-Acting-User`) : le
    fournisseur répond selon **ses** droits, avec son jeton échangé. Le worker ne reçoit que le résultat, jamais un
    jeton. Une erreur métier n'est pas une erreur HTTP : elle est dans `ok` et `code`, lisible par le modèle."""
    analyse = await AnalyseRepository(db).get(body.analyse_id)
    if analyse is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analyse introuvable")
    service = KnowledgeSearchService(db, client=client, identity_tokens=identity_tokens, limiter=limiter)
    return await service.search(user, analyse.knowledge_collections, body, acting_user=x_acting_user)
