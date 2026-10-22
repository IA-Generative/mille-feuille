from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ToolSettings
from app.connectors import redis_connector
from app.core.security.acting_user import acting_user
from app.core.security.factory import RequestContext
from app.core.security.internal import verify_app_token
from app.db import get_db
from app.routers.tool_servers import get_identity_tokens
from app.schemas.tool_call import ToolCallIn, ToolCallOut, ToolDefinitionOut, ToolResolveIn, ToolResolveOut
from app.services.tools.call_limits import CallLimiter
from app.services.tools.call_service import ToolCallService
from app.services.tools.definitions import resolve_tool_definitions
from app.services.tools.identity_tokens import IdentityTokens
from app.services.tools.mcp_caller import McpToolCaller, ToolCaller

router = APIRouter(prefix="/internal/tools", tags=["Internal", "Tools"], dependencies=[Depends(verify_app_token)])


def get_tool_caller() -> ToolCaller:
    """Le client réseau des serveurs MCP ; les tests le remplacent par un faux."""
    return McpToolCaller()


def get_call_limiter() -> CallLimiter:
    settings = ToolSettings()
    return CallLimiter(
        redis_connector.client, per_run=settings.TOOL_CALLS_PER_RUN, per_minute=settings.TOOL_CALLS_PER_MINUTE
    )


@router.post("/resolve", response_model=ToolResolveOut)
async def resolve_tools(
    body: ToolResolveIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(acting_user)],
) -> ToolResolveOut:
    """Les définitions des tools MCP qu'un agent peut utiliser, pour la personne transmise (`X-Acting-User`) : nom,
    description, schéma des arguments. Ce que la personne ne peut pas utiliser n'est pas renvoyé, mais listé."""
    definitions, unavailable = await resolve_tool_definitions(db, user, body.tool_ids)
    return ToolResolveOut(
        tools=[ToolDefinitionOut(**vars(definition)) for definition in definitions], unavailable=unavailable
    )


@router.post("/{tool_id}/call", response_model=ToolCallOut)
async def call_tool(
    tool_id: str,
    body: ToolCallIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(acting_user)],
    caller: Annotated[ToolCaller, Depends(get_tool_caller)],
    identity_tokens: Annotated[IdentityTokens, Depends(get_identity_tokens)],
    limiter: Annotated[CallLimiter, Depends(get_call_limiter)],
    x_acting_user: Annotated[str | None, Header()] = None,
) -> ToolCallOut:
    """Appelle un tool MCP au nom de la personne transmise (`X-Acting-User`). Le worker ne reçoit que le résultat :
    aucun jeton ne passe par lui. Une erreur métier n'est pas une erreur HTTP : elle est dans `ok` et `code`, lisible
    par le modèle."""
    service = ToolCallService(db, caller=caller, identity_tokens=identity_tokens, limiter=limiter)
    outcome, duration_ms = await service.call(
        user, tool_id, body.arguments, acting_user=x_acting_user, run_id=body.run_id
    )
    return ToolCallOut(
        ok=outcome.ok, code=outcome.code, output=outcome.output, truncated=outcome.truncated, duration_ms=duration_ms
    )
