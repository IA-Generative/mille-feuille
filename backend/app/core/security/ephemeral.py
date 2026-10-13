import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.repositories.app_token_repository import AppTokenRepository


@dataclass
class EphemeralIdentity:
    """Identité de l'appelant d'un endpoint /api/ephemeral/* - stockée comme
    `created_by` sur les ressources éphémères, pour le scoping de visibilité
    (voir docs/ephemeral-api.md, section Authentification)."""

    id: str
    is_app_token: bool


async def get_ephemeral_identity(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> EphemeralIdentity:
    """Les endpoints éphémères acceptent un jeton API (compte de service,
    header X-App-Token ou Authorization: Bearer, même mécanisme que /api/internal/*) ou une session
    Keycloak standard - contrairement à /api/internal/*, pas de bypass par
    INTERNAL_WORKER_TOKEN : ce jeton fixe n'identifie personne en particulier,
    inadapté pour `created_by`."""
    x_app_token = request.headers.get("X-App-Token")
    if x_app_token:
        app_token = await AppTokenRepository(db).verify(x_app_token)
        if app_token is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Jeton invalide")
        return EphemeralIdentity(id=str(app_token.id), is_app_token=True)
    # La clé d'API est aussi acceptée en `Authorization: Bearer <clé>`. Un jeton Bearer qui n'est pas une clé
    # d'API (un access token Keycloak) n'est pas rejeté ici : il passe à la vérification Keycloak ci-dessous.
    bearer = request.headers.get("Authorization", "")
    if bearer.startswith("Bearer "):
        app_token = await AppTokenRepository(db).verify(bearer.removeprefix("Bearer "))
        if app_token is not None:
            return EphemeralIdentity(id=str(app_token.id), is_app_token=True)
    # get_current_user n'est pas déclaré comme Depends() sur cette fonction
    # (l'auth par jeton API doit marcher sans lui) : FastAPI ne le résout
    # donc jamais tout seul, et un appel direct get_current_user(request)
    # contournerait silencieusement app.dependency_overrides[get_current_user]
    # (utilisé par les tests pour simuler un autre utilisateur Keycloak) -
    # on consulte les overrides nous-mêmes pour rester compatible.
    verifier: Callable[..., RequestContext] = request.app.dependency_overrides.get(get_current_user, get_current_user)
    # Un override de test suit la convention de ce repo (ex.
    # test_dossiers.py: `def as_other_user() -> RequestContext`, zéro
    # paramètre) plutôt que la signature réelle de get_current_user - on ne
    # peut pas passer `request` en aveugle aux deux.
    user = verifier(request) if inspect.signature(verifier).parameters else verifier()
    return EphemeralIdentity(id=user.user_id, is_app_token=False)
