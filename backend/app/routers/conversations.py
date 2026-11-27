from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.repositories.conversation_search_repository import ConversationSearchRepository
from app.repositories.dossier_repository import DossierRepository
from app.schemas.conversation_search import ConversationSearchIn, ConversationSearchResultOut
from app.schemas.dossier import ConversationSummaryOut
from app.schemas.pagination import Page

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=Page[ConversationSummaryOut])
async def list_my_conversations(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ConversationSummaryOut]:
    """Toutes les conversations de l'utilisateur courant, tous dossiers
    confondus - pour la liste façon ChatGPT dans la sidebar. Rien à passer
    en paramètre : list_conversations_for_user filtre déjà par
    user.user_id, jamais un id fourni par le client."""
    conversations, total = await DossierRepository(db).list_conversations_for_user_paginated(
        user_id=user.user_id, page=page, page_size=page_size, user=user
    )
    return Page.of(list(conversations), total=total, page=page, page_size=page_size)


@router.post("/search", response_model=Page[ConversationSearchResultOut])
async def search_my_conversations(
    payload: ConversationSearchIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> Page[ConversationSearchResultOut]:
    """Cherche dans ses propres conversations (messages et nom du dossier), sur les dossiers encore visibles.
    Un `POST` : les mots cherchés ne doivent apparaître ni dans l'URL ni dans les journaux d'accès."""
    results, total = await ConversationSearchRepository(db).search(
        user=user, query=payload.query, page=payload.page, page_size=payload.page_size
    )
    return Page.of(results, total=total, page=payload.page, page_size=payload.page_size)
