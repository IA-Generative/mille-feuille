"""Le jeton à présenter à un serveur MCP au nom d'une personne : sa session (rafraîchie à la demande), puis l'échange
Keycloak pour l'audience du serveur, avec un cache court. Tout reste dans le backend : aucun jeton ne passe par le
worker ni par le navigateur."""

import asyncio
import hashlib
import logging
from typing import Protocol

from redis import Redis

from app.services.tools.credentials_errors import CredentialsUnavailableError
from app.services.tools.token_exchange import TokenExchanger

logger = logging.getLogger(__name__)

CACHE_PREFIX = "millefeuille:tools:exchanged:"
# Un jeton échangé n'est gardé que s'il vit plus longtemps que cette marge, et jusqu'à cette marge avant son terme.
EXPIRY_MARGIN_SECONDS = 30


class SessionTokens(Protocol):
    def access_token_for_user(self, user_id: str) -> str | None: ...


class IdentityTokens:
    def __init__(self, sessions: SessionTokens, exchanger: TokenExchanger, cache: Redis) -> None:
        self._sessions = sessions
        self._exchanger = exchanger
        self._cache = cache

    @staticmethod
    def _cache_key(user_id: str, audience: str) -> str:
        return f"{CACHE_PREFIX}{user_id}:{hashlib.sha256(audience.encode()).hexdigest()[:16]}"

    async def token_for(self, user_id: str | None, audience: str | None) -> str:
        """Le jeton d'accès de `user_id` pour `audience`. Lève `CredentialsUnavailableError` avec un code stable."""
        if not user_id:
            raise CredentialsUnavailableError("identite_absente", "Aucune personne n'est associée à cet appel.")
        if not audience:
            raise CredentialsUnavailableError(
                "audience_manquante", "Ce serveur n'a pas d'audience Keycloak configurée."
            )

        key = self._cache_key(user_id, audience)
        cached = await asyncio.to_thread(self._cache.get, key)
        if cached:
            return cached if isinstance(cached, str) else cached.decode()

        subject_token = await asyncio.to_thread(self._sessions.access_token_for_user, user_id)
        if subject_token is None:
            raise CredentialsUnavailableError(
                "session_requise", "Votre session a expiré : reconnectez-vous pour utiliser ce serveur."
            )
        try:
            exchanged = await asyncio.to_thread(self._exchanger.exchange, subject_token, audience)
        except Exception as error:
            # Le détail vient de Keycloak : on le journalise sans le renvoyer à la personne ni au modèle.
            logger.warning("Échange de jeton refusé pour l'audience %s : %s", audience, error)
            raise CredentialsUnavailableError(
                "echange_refuse", "Keycloak a refusé l'échange de jeton pour ce serveur."
            ) from error

        ttl = exchanged.expires_in - EXPIRY_MARGIN_SECONDS
        if ttl > 0:
            await asyncio.to_thread(self._cache.set, key, exchanged.access_token, ex=ttl)
        return exchanged.access_token
