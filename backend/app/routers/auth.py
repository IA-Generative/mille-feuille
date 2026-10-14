import base64
import hashlib
import secrets
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import KeycloakSettings
from app.core.security.claims import decode_access_token, extract_identity
from app.core.security.factory import RequestContext, get_current_user
from app.core.security.keycloak_client import keycloak_openid, session_store
from app.core.security.session import PendingAuth
from app.db import get_db
from app.repositories.user_directory_repository import UserDirectoryRepository

router = APIRouter(tags=["Auth"])

# Exposed as module attributes (rather than closed over) so tests can swap
# them out with monkeypatch.setattr without a live Keycloak or Redis.
_keycloak_settings = KeycloakSettings()
_keycloak_openid = keycloak_openid
_session_store = session_store

LOGIN_RATE_LIMIT = 20
LOGIN_RATE_WINDOW_SECONDS = 60


def _is_safe_internal_path(path: str) -> bool:
    """Rejects anything that could send the browser off-site after login
    (e.g. "//evil.com" or "https://evil.com") - only "/foo/bar" is allowed."""
    return path.startswith("/") and not path.startswith("//")


def _is_allowed_redirect(target: str) -> bool:
    """Chemin interne, ou URL absolue d'un des frontends déclarés (ex. le frontend éphémère)."""
    if _is_safe_internal_path(target):
        return True
    return any(target == origin or target.startswith(f"{origin}/") for origin in _keycloak_settings.frontend_origins)


def _build_pkce_pair() -> tuple[str, str]:
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return code_verifier, code_challenge


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=_keycloak_settings.SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=_keycloak_settings.SESSION_COOKIE_SECURE,
        samesite=_keycloak_settings.SESSION_COOKIE_SAMESITE,
        max_age=_keycloak_settings.SESSION_TTL_SECONDS,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=_keycloak_settings.SESSION_COOKIE_NAME)


@router.get("/login", summary="Redirect the browser to Keycloak's login page")
async def login(request: Request, redirect: str = "/") -> RedirectResponse:
    client_ip = request.client.host if request.client else "unknown"
    if not _session_store.check_rate_limit(f"login:{client_ip}", LOGIN_RATE_LIMIT, LOGIN_RATE_WINDOW_SECONDS):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts")

    next_path = redirect if _is_allowed_redirect(redirect) else "/"
    code_verifier, code_challenge = _build_pkce_pair()
    state = secrets.token_urlsafe(32)
    _session_store.save_pending(state, PendingAuth(code_verifier=code_verifier, next_path=next_path))

    # Built by hand against the browser-facing public_url: keycloak_openid's
    # own auth_url() resolves against the backend-internal KEYCLOAK_URL, which
    # the browser (unlike the backend) usually cannot reach.
    query = urlencode(
        {
            "client_id": _keycloak_settings.KEYCLOAK_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": _keycloak_settings.callback_url,
            "scope": "openid profile email",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    realm_auth_endpoint = (
        f"{_keycloak_settings.public_url}/realms/{_keycloak_settings.KEYCLOAK_REALM}/protocol/openid-connect/auth"
    )
    auth_url = f"{realm_auth_endpoint}?{query}"
    return RedirectResponse(url=auth_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/callback", summary="Exchange the Keycloak authorization code for a session")
async def callback(code: str, state: str) -> RedirectResponse:
    pending = _session_store.pop_pending(state)
    if pending is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired login attempt")

    try:
        token_response = _keycloak_openid.token(
            grant_type="authorization_code",
            code=code,
            redirect_uri=_keycloak_settings.callback_url,
            code_verifier=pending.code_verifier,
        )
        claims = _keycloak_openid.userinfo(token_response["access_token"])
        # userinfo does not include resource_access (client roles), so we
        # decode the JWT payload to enrich the claims with role information.
        jwt_claims = decode_access_token(token_response["access_token"])
        claims = {**claims, "resource_access": jwt_claims.get("resource_access", {})}
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Login failed") from error

    identity = extract_identity(claims, _keycloak_settings.KEYCLOAK_CLIENT_ID)
    if identity is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not resolve identity")

    session_id = _session_store.create_session(identity, token_response)
    is_absolute = not pending.next_path.startswith("/")
    response = RedirectResponse(
        url=pending.next_path if is_absolute else f"{_keycloak_settings.FRONTEND_URL}{pending.next_path}",
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
    _set_session_cookie(response, session_id)
    return response


@router.post("/token", summary="Password grant for non-browser clients (scripts, SDK)")
async def token(username: str, password: str) -> dict:
    try:
        return _keycloak_openid.token(grant_type="password", username=username, password=password)
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials") from error


@router.post("/refresh", summary="Refresh grant for non-browser clients (scripts, SDK)")
async def refresh(refresh_token: str) -> dict:
    try:
        return _keycloak_openid.refresh_token(refresh_token)
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from error


@router.post("/logout", summary="End the BFF session and the Keycloak SSO session")
async def logout(request: Request, response: Response) -> dict:
    session_id = request.cookies.get(_keycloak_settings.SESSION_COOKIE_NAME)
    id_token: str | None = None
    if session_id:
        session = _session_store.get_session(session_id)
        if session:
            id_token = session.id_token
            try:
                _keycloak_openid.logout(session.refresh_token)
            except Exception:
                pass
        _session_store.delete_session(session_id)

    _clear_session_cookie(response)
    # id_token_hint proves this /logout call isn't a forged cross-site request,
    # which is what lets Keycloak redirect straight back instead of stopping
    # on its own "do you want to log out?" confirmation page.
    query = urlencode(
        {
            "client_id": _keycloak_settings.KEYCLOAK_CLIENT_ID,
            "post_logout_redirect_uri": _keycloak_settings.FRONTEND_URL,
            **({"id_token_hint": id_token} if id_token else {}),
        }
    )
    end_session_url = (
        f"{_keycloak_settings.public_url}/realms/{_keycloak_settings.KEYCLOAK_REALM}"
        f"/protocol/openid-connect/logout?{query}"
    )
    return {"redirectUrl": end_session_url}


@router.get("/me", summary="Return the current user's profile")
async def me(
    user: Annotated[RequestContext, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RequestContext:
    # Appelé à chaque ouverture de l'application : sert à tenir l'annuaire local à jour (#173).
    await UserDirectoryRepository(db).touch(user)
    return user
