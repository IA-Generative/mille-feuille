"""L'appel d'un tool MCP au nom d'une personne, de bout en bout : quotas, droits, garde d'URL, authentification, appel,
sortie bornée, journal. Aucune erreur métier n'est une exception : le worker (et le modèle) reçoivent toujours un
`ToolCallOutcome` avec un code stable."""

import json
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ToolSettings
from app.core.security.factory import RequestContext
from app.models.tool import Tool, ToolServer
from app.repositories.tool_call_log_repository import ToolCallLogRepository
from app.repositories.tool_server_repository import ToolServerRepository
from app.services.tools.call_limits import CallLimiter
from app.services.tools.call_result import ToolCallOutcome, bound_output
from app.services.tools.credentials import CredentialsUnavailableError, headers_for
from app.services.tools.identity_tokens import IdentityTokens
from app.services.tools.internal_catalog import get_internal_tool
from app.services.tools.mcp_caller import CallFailedError, CallTimeoutError, ToolCaller
from app.services.tools.url_guard import UnsafeUrlError, ensure_safe_url
from app.services.tools.visibility import can_view

MAX_ARGUMENTS_CHARS = 50_000


class ToolCallService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        caller: ToolCaller,
        identity_tokens: IdentityTokens,
        limiter: CallLimiter,
        settings: ToolSettings | None = None,
    ) -> None:
        self._db = db
        self._caller = caller
        self._identity_tokens = identity_tokens
        self._limiter = limiter
        self._settings = settings or ToolSettings()

    async def call(
        self,
        user: RequestContext,
        tool_id: str,
        arguments: dict[str, Any],
        *,
        acting_user: str | None,
        run_id: str | None = None,
    ) -> tuple[ToolCallOutcome, int]:
        """Renvoie le résultat et la durée en millisecondes ; journalise l'appel quelle qu'en soit l'issue."""
        started = time.monotonic()
        resolved = await self.resolve(user, tool_id)
        if isinstance(resolved, ToolCallOutcome):
            tool, server, outcome = None, None, resolved
        else:
            tool, server = resolved
            outcome = await self._execute(user, tool, server, arguments, acting_user=acting_user, run_id=run_id)
        duration_ms = int((time.monotonic() - started) * 1000)
        await ToolCallLogRepository(self._db).add(
            user_id=user.user_id,
            server_id=server.id if server else None,
            server_name=server.name if server else "",
            tool_name=tool.name if tool else tool_id[:100],
            run_id=run_id,
            duration_ms=duration_ms,
            outcome="ok" if outcome.ok else (outcome.code or "erreur"),
        )
        return outcome, duration_ms

    async def resolve(self, user: RequestContext, tool_id: str) -> tuple[Tool, ToolServer] | ToolCallOutcome:
        """Le tool et son serveur. Un serveur invisible pour la personne répond « inconnu »."""
        try:
            parsed = uuid.UUID(tool_id)
        except ValueError:
            return ToolCallOutcome.failure("outil_interne" if get_internal_tool(tool_id) else "outil_inconnu")
        found = await ToolServerRepository(self._db).tools_with_servers([parsed])
        if not found:
            return ToolCallOutcome.failure("outil_inconnu")
        tool, server = found[0]
        visible = can_view(
            user_id=user.user_id,
            is_admin=user.is_admin,
            groups=user.groups,
            owner_id=server.created_by,
            visibility=server.visibility,
            server_groups=server.groups,
        )
        return (tool, server) if visible else ToolCallOutcome.failure("outil_inconnu")

    async def _execute(
        self,
        user: RequestContext,
        tool: Tool,
        server: ToolServer,
        arguments: dict[str, Any],
        *,
        acting_user: str | None,
        run_id: str | None,
    ) -> ToolCallOutcome:
        if not tool.enabled:
            return ToolCallOutcome.failure("outil_desactive")
        if len(json.dumps(arguments)) > MAX_ARGUMENTS_CHARS:
            return ToolCallOutcome.failure("arguments_trop_longs")
        if not await self._limiter.allow(user.user_id, run_id):
            return ToolCallOutcome.failure("quota_depasse")
        try:
            url = await ensure_safe_url(server.url, self._settings)
            headers = await headers_for(
                server.auth_mode,
                acting_user=acting_user,
                audience=server.audience,
                identity_tokens=self._identity_tokens,
            )
            raw = await self._caller.call_tool(
                url, headers, tool.name, arguments, self._settings.TOOL_CALL_TIMEOUT_SECONDS
            )
        except UnsafeUrlError:
            return ToolCallOutcome.failure("adresse_refusee")
        except CredentialsUnavailableError as error:
            return ToolCallOutcome.failure(error.code, error.message)
        except CallTimeoutError:
            return ToolCallOutcome.failure("delai_depasse")
        except CallFailedError:
            return ToolCallOutcome.failure("serveur_indisponible")
        text, truncated = bound_output(raw.text, self._settings.TOOL_OUTPUT_MAX_CHARS)
        if raw.is_error:
            return ToolCallOutcome(ok=False, code="outil_en_erreur", output=text, truncated=truncated)
        return ToolCallOutcome(ok=True, output=text, truncated=truncated)
