"""Échange de jeton Keycloak (RFC 8693) : le jeton de la personne contre un jeton destiné à un serveur MCP (son
`audience`). Le client Keycloak est isolé derrière `TokenExchanger` : les tests le remplacent par un faux."""

from dataclasses import dataclass
from typing import Protocol

from keycloak import KeycloakOpenID

ACCESS_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"  # noqa: S105


@dataclass(frozen=True)
class ExchangedToken:
    access_token: str
    expires_in: int


class TokenExchanger(Protocol):
    def exchange(self, subject_token: str, audience: str) -> ExchangedToken: ...


class KeycloakTokenExchanger:
    """Appel bloquant : à lancer hors de la boucle d'événements (voir `IdentityTokens`)."""

    def __init__(self, openid: KeycloakOpenID) -> None:
        self._openid = openid

    def exchange(self, subject_token: str, audience: str) -> ExchangedToken:
        # Keycloak exige le type du jeton fourni ; et python-keycloak demande un jeton de renouvellement par défaut,
        # alors qu'on veut un jeton d'accès.
        response = self._openid.exchange_token(
            subject_token,
            audience=audience,
            subject_token_type=ACCESS_TOKEN_TYPE,
            requested_token_type=ACCESS_TOKEN_TYPE,
        )
        return ExchangedToken(access_token=response["access_token"], expires_in=int(response.get("expires_in", 0)))
