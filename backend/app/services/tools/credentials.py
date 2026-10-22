"""Les en-têtes d'authentification d'un appel à un serveur MCP, selon son mode. Un seul point d'entrée : ajouter un mode
(jeton statique, compte de service) ne touche pas le reste. Aucun jeton ne passe par le worker : c'est le backend qui
appelle."""

from app.models.tool import ToolAuthMode
from app.services.tools.credentials_errors import CredentialsUnavailableError
from app.services.tools.identity_tokens import IdentityTokens

__all__ = ["CredentialsUnavailableError", "headers_for"]


def default_identity_tokens() -> IdentityTokens:
    # Importé ici : le client Keycloak et Redis ne doivent pas être chargés par un simple import du module.
    from app.connectors import redis_connector
    from app.core.security.keycloak_client import keycloak_openid, session_store
    from app.services.tools.token_exchange import KeycloakTokenExchanger

    return IdentityTokens(session_store, KeycloakTokenExchanger(keycloak_openid), redis_connector.client)


async def headers_for(
    auth_mode: ToolAuthMode,
    *,
    acting_user: str | None,
    audience: str | None = None,
    identity_tokens: IdentityTokens | None = None,
) -> dict[str, str]:
    if auth_mode == ToolAuthMode.NONE:
        return {}
    if auth_mode == ToolAuthMode.TOKEN_EXCHANGE:
        token = await (identity_tokens or default_identity_tokens()).token_for(acting_user, audience)
        return {"Authorization": f"Bearer {token}"}
    raise CredentialsUnavailableError("jeton_statique_indisponible", "Le jeton statique n'est pas encore disponible.")
