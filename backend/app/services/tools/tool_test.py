"""Le test unitaire d'un tool MCP : une demande en langage naturel, un modèle qui n'a que ce tool et choisit ses
arguments, l'appel par le proxy (mêmes droits, quotas, journal que les agents), et la sortie brute. Un tool qui modifie
des données s'exécute pour de vrai : il demande une confirmation explicite."""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext
from app.services.tools.call_result import ToolCallOutcome
from app.services.tools.call_service import ToolCallService
from app.services.tools.model_chooser import ModelUnavailableError, ToolChooser, ToolSpec
from app.services.usage_service import UsageService

STEP = "test_tool"


@dataclass(frozen=True)
class ToolTestOutcome:
    outcome: ToolCallOutcome
    duration_ms: int = 0
    model: str | None = None
    # L'appel que le modèle a fait : le nom du tool et les arguments qu'il a choisis.
    call: dict[str, Any] | None = field(default=None)


class ToolTestService:
    def __init__(self, db: AsyncSession, *, chooser: ToolChooser, calls: ToolCallService) -> None:
        self._db = db
        self._chooser = chooser
        self._calls = calls

    async def run(
        self, user: RequestContext, tool_id: str, prompt: str, *, model: str | None, confirmed: bool
    ) -> ToolTestOutcome:
        resolved = await self._calls.resolve(user, tool_id)
        if isinstance(resolved, ToolCallOutcome):
            return ToolTestOutcome(resolved)
        tool, _server = resolved
        if tool.side_effect and not confirmed:
            return ToolTestOutcome(ToolCallOutcome.failure("confirmation_requise"))

        try:
            chosen = await self._chooser.choose(model, prompt, ToolSpec(tool.name, tool.description, tool.input_schema))
        except ModelUnavailableError as error:
            return ToolTestOutcome(ToolCallOutcome.failure("modele_indisponible", str(error)))
        await UsageService(self._db).record_quietly(
            STEP, chosen.model, chosen.input_tokens, chosen.output_tokens, user.user_id
        )
        if chosen.arguments is None:
            message = chosen.answer or None
            return ToolTestOutcome(ToolCallOutcome.failure("aucun_appel", message), model=chosen.model)

        outcome, duration_ms = await self._calls.call(
            user, tool_id, chosen.arguments, acting_user=user.user_id, run_id=f"test-{uuid.uuid4().hex[:12]}"
        )
        return ToolTestOutcome(
            outcome,
            duration_ms=duration_ms,
            model=chosen.model,
            call={"name": tool.name, "arguments": chosen.arguments},
        )
