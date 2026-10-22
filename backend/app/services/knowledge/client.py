"""Le client du contrat d'un fournisseur de collections : lister, retrouver par identifiant, chercher.

Il ne fait **ni garde d'URL ni authentification** : l'appelant lui donne l'URL déjà vérifiée et les en-têtes (voir
`connection.check_source` et services/tools/credentials). Il fait respecter les bornes : délai, taille de réponse lue,
texte de chaque passage. Les erreurs sont à code stable (`KnowledgeError`) et à message français fixe : le message d'un
fournisseur tiers n'est jamais relayé tel quel.

Un échec partiel n'est pas un échec : une collection indisponible est listée dans `skipped`, la recherche réussit avec
les autres. Seul un fournisseur qui n'a **aucune** collection utilisable répond en erreur."""

from typing import Any, Protocol

import httpx2
from pydantic import BaseModel, ValidationError

from app.config import ToolSettings
from app.services.knowledge.contract import (
    MAX_ANSWER_CHARS,
    MAX_COLLECTION_IDS,
    CollectionPage,
    LookupResult,
    SearchRequest,
    SearchResult,
)

ERROR_CODES = {
    "unauthorized",
    "forbidden",
    "not_found",
    "invalid_request",
    "no_usable_collection",
    "rate_limited",
    "unavailable",
    "not_implemented",
}

MESSAGES = {
    "unauthorized": "Le fournisseur a refusé l'authentification.",
    "forbidden": "Vous n'avez pas accès à cette ressource du fournisseur.",
    "not_found": "Cette ressource n'existe pas chez le fournisseur.",
    "invalid_request": "Le fournisseur a refusé la requête.",
    "no_usable_collection": "Aucune des collections demandées n'est utilisable.",
    "rate_limited": "Le fournisseur reçoit trop de requêtes : réessayez dans un instant.",
    "unavailable": "Le fournisseur ne répond pas.",
    "not_implemented": "Cette fonction n'est pas disponible chez ce fournisseur.",
    "invalid_response": "La réponse du fournisseur ne respecte pas le contrat de la base de connaissances.",
    "not_json": "La réponse du fournisseur n'est pas du JSON.",
    "too_large": "La réponse du fournisseur est trop volumineuse.",
}

STATUS_CODES = {401: "unauthorized", 403: "forbidden", 404: "not_found", 422: "invalid_request", 429: "rate_limited"}


class KnowledgeError(Exception):
    """Le fournisseur n'a pas pu répondre ; `code` est stable, `message` est affichable."""

    def __init__(self, code: str) -> None:
        super().__init__(MESSAGES[code])
        self.code = code
        self.message = MESSAGES[code]


class KnowledgeClient(Protocol):
    async def list_collections(
        self, url: str, headers: dict[str, str], *, page: int, page_size: int, q: str | None
    ) -> CollectionPage: ...

    async def lookup(self, url: str, headers: dict[str, str], ids: list[str]) -> LookupResult: ...

    async def search(self, url: str, headers: dict[str, str], request: SearchRequest) -> SearchResult: ...


def _error_code(response: httpx2.Response) -> str:
    """Le code de l'erreur : celui du contrat s'il est reconnu, sinon déduit du statut HTTP."""
    try:
        code = response.json().get("code")
    except (ValueError, AttributeError):
        code = None
    if code in ERROR_CODES:
        return code
    return STATUS_CODES.get(response.status_code, "unavailable")


class HttpKnowledgeClient:
    """Client réel. `transport` sert aux tests (appel en mémoire)."""

    def __init__(
        self, transport: httpx2.AsyncBaseTransport | None = None, settings: ToolSettings | None = None
    ) -> None:
        self._transport = transport
        self._settings = settings or ToolSettings()

    async def _request[T: BaseModel](
        self,
        model: type[T],
        method: str,
        url: str,
        path: str,
        headers: dict[str, str],
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> T:
        try:
            # Les redirections ne sont pas suivies : la garde d'URL n'a validé que l'adresse donnée.
            async with httpx2.AsyncClient(
                headers=headers, timeout=self._settings.TOOL_CALL_TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.request(method, f"{url.rstrip('/')}{path}", params=params, json=json)
        except httpx2.HTTPError as error:
            raise KnowledgeError("unavailable") from error
        if response.status_code != 200:
            raise KnowledgeError(_error_code(response))
        if len(response.content) > self._settings.KNOWLEDGE_RESPONSE_MAX_BYTES:
            raise KnowledgeError("too_large")
        try:
            body = response.json()
        except ValueError as error:
            raise KnowledgeError("not_json") from error
        try:
            return model.model_validate(body)
        except ValidationError as error:
            raise KnowledgeError("invalid_response") from error

    async def list_collections(
        self, url: str, headers: dict[str, str], *, page: int, page_size: int, q: str | None
    ) -> CollectionPage:
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if q:
            params["q"] = q
        return await self._request(CollectionPage, "GET", url, "/v1/collections", headers, params=params)

    async def lookup(self, url: str, headers: dict[str, str], ids: list[str]) -> LookupResult:
        unique = list(dict.fromkeys(ids))
        if not unique or len(unique) > 100:
            raise KnowledgeError("invalid_request")
        return await self._request(LookupResult, "POST", url, "/v1/collections/lookup", headers, json={"ids": unique})

    async def search(self, url: str, headers: dict[str, str], request: SearchRequest) -> SearchResult:
        body = request.model_dump(exclude_none=True)
        body["collection_ids"] = list(dict.fromkeys(request.collection_ids))[:MAX_COLLECTION_IDS]
        result = await self._request(SearchResult, "POST", url, "/v1/search", headers, json=body)
        for source in result.sources:
            if len(source.passage) > request.max_chars:
                source.passage, source.truncated = source.passage[: request.max_chars], True
        if result.answer is not None and len(result.answer) > MAX_ANSWER_CHARS:
            result.answer, result.answer_truncated = result.answer[:MAX_ANSWER_CHARS], True
        return result
