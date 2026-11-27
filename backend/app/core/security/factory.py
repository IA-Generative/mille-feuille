import os
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import KeycloakSettings
from app.core.security.claims import decode_access_token, extract_identity
from app.core.security.keycloak_client import keycloak_openid, session_store
from app.db import get_db
from app.services.memberships import apply_memberships


@dataclass
class RequestContext:
    user_id: str
    email: str
    roles: list[str]
    is_admin: bool
    first_name: str = ""
    last_name: str = ""
    # Identifiants des groupes de l'application dont la personne est membre.
    groups: list[str] = field(default_factory=list)
    # Seule une adresse vérifiée rattache les places réservées à cette adresse.
    email_verified: bool = False


class KeycloakToken:
    """Real verifier: a bearer access token (non-browser clients) or the BFF
    session cookie set by /api/auth/callback (browser clients)."""

    def __init__(self) -> None:
        self._keycloak_settings = KeycloakSettings()

    def __call__(self, request: Request) -> RequestContext:
        identity = self._from_bearer_token(request) or self._from_session_cookie(request)
        if identity is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        return RequestContext(**identity)

    def _from_bearer_token(self, request: Request) -> dict | None:
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return None
        token = authorization.removeprefix("Bearer ")
        try:
            # userinfo, not introspect: introspection requires the caller to be
            # in the token's own audience, which a resource server usually isn't.
            claims = keycloak_openid.userinfo(token)
            # userinfo does not include resource_access (client roles), so we
            # decode the JWT payload to enrich the claims with role information.
            jwt_claims = decode_access_token(token)
            claims = {**claims, "resource_access": jwt_claims.get("resource_access", {})}
        except Exception:
            return None
        return extract_identity(claims, self._keycloak_settings.KEYCLOAK_CLIENT_ID)

    def _from_session_cookie(self, request: Request) -> dict | None:
        session_id = request.cookies.get(self._keycloak_settings.SESSION_COOKIE_NAME)
        if not session_id:
            return None
        session = session_store.get_session(session_id)
        if session is None:
            return None
        return session.identity


class AllowAllAccess:
    """Dev/test verifier: no Keycloak, no Redis - a fixed identity for every
    request. Selected via VERIFY_TOKEN_MODEL=full-access (CI unit tests)."""

    def __call__(self, request: Request) -> RequestContext:
        # Un groupe de test : un dossier créé par l'API est restreint par défaut (issue #177) et a besoin d'au moins un
        # groupe. L'identité reste administrateur.
        return RequestContext(
            user_id="dev-user", email="dev@example.com", roles=["admin"], is_admin=True, groups=["/dev-tests"]
        )


SECURITY_FACTORY = {"full-access": AllowAllAccess, "keycloak": KeycloakToken}


def get_token_verifier():
    strategy = SECURITY_FACTORY[os.environ.get("VERIFY_TOKEN_MODEL", "keycloak")]
    return strategy()


TokenVerifier = get_token_verifier()

# Declared purely so Swagger UI shows an "Authorize" button and lets a bearer
# token be tested from /api/docs - the actual token extraction/verification
# still happens inside KeycloakToken._from_bearer_token above, unaffected by
# this dependency. auto_error=False: a request with no/invalid Authorization
# header must still be able to fall through to the BFF session cookie below,
# never get rejected here before that check runs.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Keycloak access token. Browser clients authenticate via the BFF session "
    "cookie instead - this is only for testing endpoints directly from Swagger UI.",
)
_bearer_security = Security(bearer_scheme)


async def authenticate(request: Request, db: AsyncSession) -> RequestContext:
    """Qui est là (Keycloak), puis ses groupes, lus en base à chaque requête : un retrait vaut dès la suivante."""
    # La vérification appelle Keycloak de façon bloquante : hors de la boucle d'événements.
    user = await run_in_threadpool(TokenVerifier, request)
    if isinstance(TokenVerifier, KeycloakToken):
        await apply_memberships(db, user)
    return user


_database = Depends(get_db)


async def get_current_user(
    request: Request,
    db: AsyncSession = _database,
    _credentials: HTTPAuthorizationCredentials | None = _bearer_security,
) -> RequestContext:
    return await authenticate(request, db)
