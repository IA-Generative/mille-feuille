"""Vérification de la connexion à une source de connaissances : garde d'URL, en-têtes d'authentification, puis un
appel du contrat (`GET /v1/collections`, une page d'un élément). C'est le seul chemin qui parle à un fournisseur ajouté
par une personne ; la garde et l'authentification sont celles des serveurs MCP (services/tools), pas une copie.

Le client réseau est isolé derrière `SourceProbe` : les routes en dépendent, les tests le remplacent par un faux."""

from typing import Protocol

import httpx2

from app.config import ToolSettings
from app.models.tool import ToolAuthMode
from app.services.tools.credentials import headers_for
from app.services.tools.identity_tokens import IdentityTokens
from app.services.tools.url_guard import ensure_safe_url


class ProbeError(Exception):
    """Le fournisseur ne répond pas, ou pas comme le contrat le demande ; le message est affichable."""


class SourceProbe(Protocol):
    async def probe(self, url: str, headers: dict[str, str], timeout: float) -> None: ...


class HttpSourceProbe:
    """Client réel. `transport` sert aux tests (appel en mémoire)."""

    def __init__(self, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def probe(self, url: str, headers: dict[str, str], timeout: float) -> None:
        try:
            async with httpx2.AsyncClient(headers=headers, timeout=timeout, transport=self._transport) as client:
                # Les redirections ne sont pas suivies : la garde d'URL n'a validé que l'adresse donnée.
                response = await client.get(f"{url.rstrip('/')}/v1/collections", params={"page_size": 1})
        except httpx2.HTTPError as error:
            raise ProbeError("Le fournisseur ne répond pas.") from error
        if response.status_code in (401, 403):
            raise ProbeError("Le fournisseur a refusé l'authentification.")
        if response.status_code != 200:
            raise ProbeError("Le fournisseur ne répond pas comme le contrat de la base de connaissances.")
        try:
            body = response.json()
        except ValueError as error:
            raise ProbeError("La réponse du fournisseur n'est pas du JSON.") from error
        if not isinstance(body, dict) or not isinstance(body.get("items"), list):
            raise ProbeError("La réponse du fournisseur ne respecte pas le contrat (liste de collections attendue).")


async def check_source(
    url: str,
    auth_mode: ToolAuthMode,
    *,
    acting_user: str | None,
    probe: SourceProbe,
    audience: str | None = None,
    identity_tokens: IdentityTokens | None = None,
) -> str:
    """Renvoie l'URL vérifiée. Lève `UnsafeUrlError`, `CredentialsUnavailableError` ou `ProbeError` : la route les
    traduit en réponses."""
    settings = ToolSettings()
    safe_url = await ensure_safe_url(url, settings)
    headers = await headers_for(auth_mode, acting_user=acting_user, audience=audience, identity_tokens=identity_tokens)
    await probe.probe(safe_url, headers, settings.TOOL_DISCOVERY_TIMEOUT_SECONDS)
    return safe_url
