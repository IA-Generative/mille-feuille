import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.models.knowledge_source import KnowledgeSource
from app.models.tool import ToolAuthMode
from app.repositories.knowledge_source_repository import KnowledgeSourceRepository
from app.routers.tool_servers import get_identity_tokens
from app.schemas.knowledge_source import KnowledgeSourceCreate, KnowledgeSourceOut
from app.schemas.pagination import Page
from app.services.knowledge.client import HttpKnowledgeClient, KnowledgeClient, KnowledgeError
from app.services.knowledge.connection import HttpSourceProbe, ProbeError, SourceProbe, check_source, prepare_call
from app.services.knowledge.contract import Collection
from app.services.tools.credentials import CredentialsUnavailableError
from app.services.tools.identity_tokens import IdentityTokens
from app.services.tools.url_guard import UnsafeUrlError
from app.services.tools.visibility import can_view_server

router = APIRouter(prefix="/knowledge-sources", tags=["Knowledge"], dependencies=[Depends(get_current_user)])


def get_knowledge_client() -> KnowledgeClient:
    """Le client réseau des fournisseurs de collections ; les tests le remplacent par un faux."""
    return HttpKnowledgeClient()


def get_source_probe(client: Annotated[KnowledgeClient, Depends(get_knowledge_client)]) -> SourceProbe:
    return HttpSourceProbe(client)


async def _check(
    url: str,
    auth_mode: ToolAuthMode,
    audience: str | None,
    user: RequestContext,
    probe: SourceProbe,
    identity_tokens: IdentityTokens,
) -> str:
    try:
        return await check_source(
            url, auth_mode, acting_user=user.user_id, probe=probe, audience=audience, identity_tokens=identity_tokens
        )
    except UnsafeUrlError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    except CredentialsUnavailableError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": error.code, "message": error.message}
        ) from error
    except ProbeError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error


async def _visible_source(source_id: uuid.UUID, db: AsyncSession, user: RequestContext) -> KnowledgeSource:
    """Une source que la personne ne voit pas répond 404, comme si elle n'existait pas."""
    source = await KnowledgeSourceRepository(db).get(source_id)
    if source is None or not can_view_server(user, source):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Source introuvable")
    return source


@router.get("", response_model=Page[KnowledgeSourceOut])
async def list_knowledge_sources(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[KnowledgeSourceOut]:
    sources, total = await KnowledgeSourceRepository(db).list_visible(user, query=q, page=page, page_size=page_size)
    items = [KnowledgeSourceOut.of(source, user_id=user.user_id) for source in sources]
    return Page.of(items, total=total, page=page, page_size=page_size)


@router.post("", response_model=KnowledgeSourceOut, status_code=status.HTTP_201_CREATED)
async def create_knowledge_source(
    body: KnowledgeSourceCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    probe: Annotated[SourceProbe, Depends(get_source_probe)],
    identity_tokens: Annotated[IdentityTokens, Depends(get_identity_tokens)],
) -> KnowledgeSourceOut:
    """Ajoute une source. La connexion est vérifiée avant l'enregistrement : une source qui ne répond pas comme le
    contrat n'est pas ajoutée."""
    safe_url = await _check(body.url, body.auth_mode, body.audience, user, probe, identity_tokens)
    source = await KnowledgeSourceRepository(db).create(
        name=body.name,
        url=safe_url,
        auth_mode=body.auth_mode,
        visibility=body.visibility,
        audience=body.audience,
        owner=user,
    )
    return KnowledgeSourceOut.of(source, user_id=user.user_id)


@router.get("/{source_id}", response_model=KnowledgeSourceOut)
async def get_knowledge_source(
    source_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> KnowledgeSourceOut:
    return KnowledgeSourceOut.of(await _visible_source(source_id, db, user), user_id=user.user_id)


@router.get("/{source_id}/collections", response_model=Page[Collection])
async def list_source_collections(
    source_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    client: Annotated[KnowledgeClient, Depends(get_knowledge_client)],
    identity_tokens: Annotated[IdentityTokens, Depends(get_identity_tokens)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[Collection]:
    """Les collections que **cette personne** peut voir chez le fournisseur (ses droits, pas ceux de la plateforme),
    paginées et filtrées côté fournisseur."""
    source = await _visible_source(source_id, db, user)
    try:
        url, headers = await prepare_call(
            source.url,
            source.auth_mode,
            acting_user=user.user_id,
            audience=source.audience,
            identity_tokens=identity_tokens,
        )
        result = await client.list_collections(url, headers, page=page, page_size=page_size, q=q)
    except UnsafeUrlError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    except CredentialsUnavailableError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": error.code, "message": error.message}
        ) from error
    except KnowledgeError as error:
        code = {"rate_limited": 429, "invalid_request": 422}.get(error.code, status.HTTP_502_BAD_GATEWAY)
        raise HTTPException(code, detail={"code": error.code, "message": error.message}) from error
    return Page.of(result.items, total=result.total, page=page, page_size=page_size)


@router.post("/{source_id}/check", status_code=status.HTTP_204_NO_CONTENT)
async def check_knowledge_source(
    source_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    probe: Annotated[SourceProbe, Depends(get_source_probe)],
    identity_tokens: Annotated[IdentityTokens, Depends(get_identity_tokens)],
) -> None:
    """Vérifie que la source répond toujours comme le contrat, avec l'identité de la personne qui demande."""
    source = await _visible_source(source_id, db, user)
    await _check(source.url, source.auth_mode, source.audience, user, probe, identity_tokens)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_source(
    source_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> None:
    source = await _visible_source(source_id, db, user)
    if source.created_by != user.user_id and not user.is_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Seule la personne qui l'a ajoutée peut supprimer cette source"
        )
    await KnowledgeSourceRepository(db).delete(source)
