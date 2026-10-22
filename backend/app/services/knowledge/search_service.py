"""La recherche dans la base de connaissances d'une analyse, au nom d'une personne, de bout en bout : quotas, droits sur
les sources, garde d'URL, échange de jeton, appel, sortie bornée, journal. Aucune erreur métier n'est une exception :
le worker (et le modèle) reçoivent toujours un `KnowledgeSearchOut` à code stable.

Les collections cherchées sont celles que **l'analyse** autorise ; leurs droits sont ceux de **la personne** (le
fournisseur répond selon son identité). Un fournisseur ou une collection qui échoue n'empêche pas les autres : ils sont
listés dans `skipped`. Le journal (`tool_call_logs`) compte un appel par source consultée, sans la question ni le texte
trouvé (ils peuvent contenir des données personnelles)."""

import time
import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ToolSettings
from app.core.security.factory import RequestContext
from app.repositories.knowledge_source_repository import KnowledgeSourceRepository
from app.repositories.tool_call_log_repository import ToolCallLogRepository
from app.schemas.knowledge_search import (
    KnowledgeBoxOut,
    KnowledgeSearchIn,
    KnowledgeSearchOut,
    KnowledgeSourceOut,
    SkippedCollectionOut,
)
from app.services.knowledge.client import KnowledgeClient, KnowledgeError
from app.services.knowledge.connection import prepare_call
from app.services.knowledge.contract import MAX_COLLECTION_IDS, SearchRequest
from app.services.tools.call_limits import CallLimiter
from app.services.tools.credentials import CredentialsUnavailableError
from app.services.tools.identity_tokens import IdentityTokens
from app.services.tools.url_guard import UnsafeUrlError
from app.services.tools.visibility import can_view_server

LOG_TOOL_NAME = "base_connaissances"
# Le texte de chaque passage donné au modèle : assez pour citer, pas assez pour saturer son contexte.
MAX_CHARS_PER_PASSAGE = 1500

FAILURES = {
    "aucune_collection": "Aucune collection de la base de connaissances n'est choisie pour cette analyse.",
    "quota_depasse": "Trop d'appels d'outils : réessayez dans quelques instants.",
    "aucune_collection_disponible": "Aucune des collections de la base de connaissances n'a pu être consultée.",
}


def _failure(code: str, message: str | None = None, *, skipped: list[SkippedCollectionOut] | None = None):
    return KnowledgeSearchOut(ok=False, code=code, message=message or FAILURES[code], skipped=skipped or [])


class KnowledgeSearchService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        client: KnowledgeClient,
        identity_tokens: IdentityTokens,
        limiter: CallLimiter,
        settings: ToolSettings | None = None,
    ) -> None:
        self._db = db
        self._client = client
        self._identity_tokens = identity_tokens
        self._limiter = limiter
        self._settings = settings or ToolSettings()
        self._logs = ToolCallLogRepository(db)

    async def search(
        self, user: RequestContext, collections: Sequence[dict], body: KnowledgeSearchIn, *, acting_user: str | None
    ) -> KnowledgeSearchOut:
        """`collections` : celles que l'analyse autorise (`analyses.knowledge_collections`)."""
        if not collections:
            return _failure("aucune_collection")
        if not await self._limiter.allow(user.user_id, body.run_id):
            await self._log(user, "", 0, body.run_id, "quota_depasse")
            return _failure("quota_depasse")

        sources: list[KnowledgeSourceOut] = []
        answers: list[tuple[str, str]] = []  # (réponse, nom de la source)
        skipped: list[SkippedCollectionOut] = []
        repository = KnowledgeSourceRepository(self._db)
        by_source: dict[uuid.UUID, list[dict]] = {}
        for item in collections:
            by_source.setdefault(uuid.UUID(str(item["source_id"])), []).append(item)

        for source_id, items in by_source.items():
            source = await repository.get(source_id)
            names = {item["collection_id"]: item["name"] for item in items}

            def skip(reason: str, ids: Sequence[str], source_name: str, names: dict = names) -> None:
                skipped.extend(
                    SkippedCollectionOut(
                        collection_id=i, collection_name=names[i], source_name=source_name, reason=reason
                    )
                    for i in ids
                )

            if source is None or not can_view_server(user, source):
                skip("unavailable", list(names), source.name if source else "")
                continue
            started = time.monotonic()
            try:
                url, headers = await prepare_call(
                    source.url,
                    source.auth_mode,
                    acting_user=acting_user,
                    audience=source.audience,
                    identity_tokens=self._identity_tokens,
                )
            except CredentialsUnavailableError as error:
                # Sans identité exploitable, aucune source ne répondra : c'est l'échec de toute la recherche.
                await self._log(user, source.name, started, body.run_id, error.code)
                return _failure(error.code, error.message)
            except UnsafeUrlError:
                await self._log(user, source.name, started, body.run_id, "adresse_refusee")
                skip("unavailable", list(names), source.name)
                continue

            outcome = "ok"
            for start in range(0, len(names), MAX_COLLECTION_IDS):
                ids = list(names)[start : start + MAX_COLLECTION_IDS]
                request = SearchRequest(
                    query=body.query, collection_ids=ids, top_k=body.top_k, max_chars=MAX_CHARS_PER_PASSAGE
                )
                try:
                    result = await self._client.search(url, headers, request)
                except KnowledgeError as error:
                    outcome = error.code
                    reason = error.code if error.code in ("forbidden", "not_found") else "unavailable"
                    skip(reason, ids, source.name)
                    continue
                sources.extend(
                    KnowledgeSourceOut(
                        id=p.id,
                        kind=p.kind,
                        title=p.title,
                        url=p.url,
                        preview_url=p.preview_url,
                        page=p.page,
                        boxes=[KnowledgeBoxOut(**box.model_dump()) for box in p.boxes],
                        passage=p.passage,
                        score=p.score,
                        collection_id=p.collection_id,
                        collection_name=names.get(p.collection_id, p.collection_id),
                        source_name=source.name,
                    )
                    for p in result.sources
                    if p.collection_id in names  # une source d'une collection non demandée n'est pas relayée
                )
                if result.answer:
                    answers.append((result.answer, source.name))
                skip_ids = {s.collection_id: s.reason for s in result.skipped if s.collection_id in names}
                for reason in ("not_found", "forbidden", "unavailable"):
                    skip(reason, [i for i, r in skip_ids.items() if r == reason], source.name)
            await self._log(user, source.name, started, body.run_id, outcome)

        if not sources and not answers and skipped and len(skipped) == len(collections):
            return _failure("aucune_collection_disponible", skipped=skipped)
        sources.sort(key=lambda source: source.score, reverse=True)
        sources, truncated = self._bound(sources[: body.top_k])
        # Une seule réponse est gardée : celle d'un fournisseur unique. Plusieurs fournisseurs répondraient chacun à
        # leur façon ; on ne les fusionne pas, le modèle rédige à partir des sources.
        answer = answers[0][0] if len(answers) == 1 else None
        return KnowledgeSearchOut(ok=True, answer=answer, sources=sources, skipped=skipped, truncated=truncated)

    def _bound(self, sources: list[KnowledgeSourceOut]) -> tuple[list[KnowledgeSourceOut], bool]:
        """Garde les sources les mieux classées tant que le total tient dans la taille maximale d'une sortie d'outil."""
        kept: list[KnowledgeSourceOut] = []
        total = 0
        for source in sources:
            total += len(source.passage)
            if total > self._settings.TOOL_OUTPUT_MAX_CHARS:
                return kept, True
            kept.append(source)
        return kept, False

    async def _log(
        self, user: RequestContext, source_name: str, started: float, run_id: str | None, outcome: str
    ) -> None:
        duration = int((time.monotonic() - started) * 1000) if started else 0
        await self._logs.add(
            user_id=user.user_id,
            server_id=None,
            server_name=source_name,
            tool_name=LOG_TOOL_NAME,
            run_id=run_id,
            duration_ms=duration,
            outcome=outcome,
        )
