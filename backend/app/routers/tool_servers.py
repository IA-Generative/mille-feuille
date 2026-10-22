import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.models.tool import ToolServer
from app.repositories.tool_server_repository import ToolServerRepository
from app.schemas.pagination import Page
from app.schemas.tool import DiscoveredToolOut, DiscoverIn, DiscoverOut, ToolServerCreate, ToolServerOut
from app.services.tools.credentials import CredentialsUnavailableError, default_identity_tokens
from app.services.tools.discovery import discover_tools
from app.services.tools.identity_tokens import IdentityTokens
from app.services.tools.mcp_discovery import DiscoveredTool, DiscoveryError, McpToolLister, ToolLister
from app.services.tools.url_guard import UnsafeUrlError
from app.services.tools.visibility import can_view

router = APIRouter(prefix="/tool-servers", tags=["Tools"], dependencies=[Depends(get_current_user)])


def get_tool_lister() -> ToolLister:
    """Le client réseau des serveurs MCP ; les tests le remplacent par un faux."""
    return McpToolLister()


def get_identity_tokens() -> IdentityTokens:
    """Les jetons d'identité (session + échange Keycloak) ; les tests les remplacent par un faux."""
    return default_identity_tokens()


async def _discover(
    body: DiscoverIn, user: RequestContext, lister: ToolLister, identity_tokens: IdentityTokens
) -> tuple[str, list[DiscoveredTool]]:
    try:
        return await discover_tools(
            body.url,
            body.auth_mode,
            acting_user=user.user_id,
            lister=lister,
            audience=body.audience,
            identity_tokens=identity_tokens,
        )
    except UnsafeUrlError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    except CredentialsUnavailableError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": error.code, "message": error.message}
        ) from error
    except DiscoveryError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error


async def _visible_server(server_id: uuid.UUID, db: AsyncSession, user: RequestContext) -> ToolServer:
    """Un serveur que la personne ne voit pas répond 404, comme s'il n'existait pas."""
    server = await ToolServerRepository(db).get(server_id)
    visible = server is not None and can_view(
        user_id=user.user_id,
        is_admin=user.is_admin,
        groups=user.groups,
        owner_id=server.created_by,
        visibility=server.visibility,
        server_groups=server.groups,
    )
    if not visible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Serveur introuvable")
    return server


async def _owned_server(server_id: uuid.UUID, db: AsyncSession, user: RequestContext) -> ToolServer:
    server = await _visible_server(server_id, db, user)
    if server.created_by != user.user_id and not user.is_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Seule la personne qui l'a ajouté peut modifier ce serveur"
        )
    return server


@router.post("/discover", response_model=DiscoverOut)
async def discover_server_tools(
    body: DiscoverIn,
    user: Annotated[RequestContext, Depends(get_current_user)],
    lister: Annotated[ToolLister, Depends(get_tool_lister)],
    identity_tokens: Annotated[IdentityTokens, Depends(get_identity_tokens)],
) -> DiscoverOut:
    """Liste les tools qu'un serveur expose, sans rien enregistrer (étape « importer » du formulaire d'ajout)."""
    _, tools = await _discover(body, user, lister, identity_tokens)
    return DiscoverOut(
        tools=[
            DiscoveredToolOut(name=tool.name, description=tool.description, side_effect=tool.side_effect)
            for tool in tools
        ]
    )


@router.get("", response_model=Page[ToolServerOut])
async def list_tool_servers(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ToolServerOut]:
    servers, total = await ToolServerRepository(db).list_visible(user, query=q, page=page, page_size=page_size)
    items = [ToolServerOut.of(server, user_id=user.user_id) for server in servers]
    return Page.of(items, total=total, page=page, page_size=page_size)


@router.post("", response_model=ToolServerOut, status_code=status.HTTP_201_CREATED)
async def create_tool_server(
    body: ToolServerCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    lister: Annotated[ToolLister, Depends(get_tool_lister)],
    identity_tokens: Annotated[IdentityTokens, Depends(get_identity_tokens)],
) -> ToolServerOut:
    """Ajoute un serveur. La liste des tools est relue côté serveur : on ne fait pas confiance à celle du client."""
    safe_url, tools = await _discover(body, user, lister, identity_tokens)
    unknown = sorted(set(body.tool_names) - {tool.name for tool in tools})
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Ces tools n'existent pas sur le serveur : {', '.join(unknown)}",
        )
    server = await ToolServerRepository(db).create(
        name=body.name,
        url=safe_url,
        auth_mode=body.auth_mode,
        visibility=body.visibility,
        audience=body.audience,
        owner=user,
        tools=tools,
        enabled_names=body.tool_names,
    )
    return ToolServerOut.of(server, user_id=user.user_id)


@router.get("/{server_id}", response_model=ToolServerOut)
async def get_tool_server(
    server_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> ToolServerOut:
    return ToolServerOut.of(await _visible_server(server_id, db, user), user_id=user.user_id)


@router.post("/{server_id}/refresh", response_model=ToolServerOut)
async def refresh_tool_server(
    server_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    lister: Annotated[ToolLister, Depends(get_tool_lister)],
    identity_tokens: Annotated[IdentityTokens, Depends(get_identity_tokens)],
) -> ToolServerOut:
    """Relit les tools du serveur. Les nouveaux ne sont pas autorisés d'office."""
    server = await _owned_server(server_id, db, user)
    source = DiscoverIn(url=server.url, auth_mode=server.auth_mode, audience=server.audience)
    _, tools = await _discover(source, user, lister, identity_tokens)
    server = await ToolServerRepository(db).refresh_tools(server, tools)
    return ToolServerOut.of(server, user_id=user.user_id)


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool_server(
    server_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> None:
    server = await _owned_server(server_id, db, user)
    await ToolServerRepository(db).delete(server)
