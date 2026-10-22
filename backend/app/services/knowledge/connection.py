"""Vérification de la connexion à une source de connaissances : garde d'URL, en-têtes d'authentification, puis un
appel du contrat (`GET /v1/collections`, une page d'un élément). C'est le seul chemin qui parle à un fournisseur ajouté
par une personne ; la garde et l'authentification sont celles des serveurs MCP (services/tools), pas une copie.

Le client réseau est isolé derrière `SourceProbe` : les routes en dépendent, les tests le remplacent par un faux."""

from typing import Protocol

from app.config import ToolSettings
from app.models.tool import ToolAuthMode
from app.services.knowledge.client import HttpKnowledgeClient, KnowledgeClient, KnowledgeError
from app.services.tools.credentials import headers_for
from app.services.tools.identity_tokens import IdentityTokens
from app.services.tools.url_guard import ensure_safe_url


class ProbeError(Exception):
    """Le fournisseur ne répond pas, ou pas comme le contrat le demande ; le message est affichable."""


class SourceProbe(Protocol):
    async def probe(self, url: str, headers: dict[str, str], timeout: float) -> None: ...


class HttpSourceProbe:
    """Vérifie la connexion avec le client du contrat (`list_collections`, une page d'un élément)."""

    def __init__(self, client: KnowledgeClient | None = None) -> None:
        self._client = client or HttpKnowledgeClient()

    async def probe(self, url: str, headers: dict[str, str], timeout: float) -> None:
        try:
            await self._client.list_collections(url, headers, page=1, page_size=1, q=None)
        except KnowledgeError as error:
            raise ProbeError(error.message) from error


async def prepare_call(
    url: str,
    auth_mode: ToolAuthMode,
    *,
    acting_user: str | None,
    audience: str | None = None,
    identity_tokens: IdentityTokens | None = None,
) -> tuple[str, dict[str, str]]:
    """L'URL vérifiée (garde anti-SSRF, refaite à chaque appel) et les en-têtes d'authentification, au nom de la
    personne. Lève `UnsafeUrlError` ou `CredentialsUnavailableError` : la route les traduit en réponses."""
    safe_url = await ensure_safe_url(url, ToolSettings())
    headers = await headers_for(auth_mode, acting_user=acting_user, audience=audience, identity_tokens=identity_tokens)
    return safe_url, headers


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
    safe_url, headers = await prepare_call(
        url, auth_mode, acting_user=acting_user, audience=audience, identity_tokens=identity_tokens
    )
    await probe.probe(safe_url, headers, ToolSettings().TOOL_DISCOVERY_TIMEOUT_SECONDS)
    return safe_url
