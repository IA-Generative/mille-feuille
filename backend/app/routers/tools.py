from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.routers import assist
from app.routers.internal_tools import get_call_limiter, get_tool_caller
from app.routers.tool_servers import get_identity_tokens
from app.schemas.tool import ToolOut
from app.schemas.tool_call import ToolTestCallOut, ToolTestIn, ToolTestOut
from app.services.tools.call_limits import CallLimiter
from app.services.tools.call_service import ToolCallService
from app.services.tools.identity_tokens import IdentityTokens
from app.services.tools.internal_catalog import available_internal_tools
from app.services.tools.mcp_caller import ToolCaller
from app.services.tools.model_chooser import OpenAiToolChooser, ToolChooser
from app.services.tools.tool_test import ToolTestService

router = APIRouter(prefix="/tools", tags=["Tools"], dependencies=[Depends(get_current_user)])


def get_tool_chooser() -> ToolChooser:
    """Le modèle qui choisit les arguments : le client et le modèle par défaut sont ceux de l'aide LLM."""
    return OpenAiToolChooser(assist._openai_client, assist._default_chat_model)


@router.get("/internal", response_model=list[ToolOut])
async def list_internal_tools() -> list[ToolOut]:
    """Les tools internes que les agents peuvent utiliser (toujours disponibles, non modifiables)."""
    return [ToolOut.of_internal(tool) for tool in available_internal_tools()]


@router.post("/{tool_id}/test", response_model=ToolTestOut)
async def test_tool(
    tool_id: str,
    body: ToolTestIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    chooser: Annotated[ToolChooser, Depends(get_tool_chooser)],
    caller: Annotated[ToolCaller, Depends(get_tool_caller)],
    identity_tokens: Annotated[IdentityTokens, Depends(get_identity_tokens)],
    limiter: Annotated[CallLimiter, Depends(get_call_limiter)],
) -> ToolTestOut:
    """Teste un tool MCP : le modèle n'a que ce tool et choisit ses arguments, on renvoie la sortie brute. Une erreur
    métier n'est pas une erreur HTTP : elle est dans `ok` et `code`. L'appel est fait avec **l'identité de la
    personne**, comme celui d'un agent."""
    calls = ToolCallService(db, caller=caller, identity_tokens=identity_tokens, limiter=limiter)
    result = await ToolTestService(db, chooser=chooser, calls=calls).run(
        user, tool_id, body.prompt, model=body.model, confirmed=body.confirmed
    )
    outcome = result.outcome
    return ToolTestOut(
        ok=outcome.ok,
        code=outcome.code,
        output=outcome.output,
        truncated=outcome.truncated,
        duration_ms=result.duration_ms,
        model=result.model,
        call=ToolTestCallOut(**result.call) if result.call else None,
    )
