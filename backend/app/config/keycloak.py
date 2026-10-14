from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class KeycloakSettings(BaseSettings):
    # Backend-to-Keycloak URL (Docker service name, e.g. http://keycloak:8080).
    KEYCLOAK_URL: str = "http://localhost:8080"
    # Browser-facing URL, if different (e.g. reverse-proxied). Falls back to KEYCLOAK_URL.
    KEYCLOAK_PUBLIC_URL: str | None = None
    KEYCLOAK_REALM: str = "mille-feuille"
    KEYCLOAK_CLIENT_ID: str = "mille-feuille-backend"
    KEYCLOAK_CLIENT_SECRET: str | None = None

    # Used to build the fixed OAuth2 redirect_uri registered in the Keycloak client.
    BACKEND_PUBLIC_URL: str = "http://localhost:8000"
    # Where the browser lands after login/logout.
    FRONTEND_URL: str = "http://localhost:5173"
    # Frontend autonome de l'API éphémère (ephemeral-frontend/) : autorisé en CORS et comme cible de redirection
    # post-login. Vide = le frontend principal est le seul.
    EPHEMERAL_FRONTEND_URL: str | None = None

    SESSION_COOKIE_NAME: str = "millefeuille_session"
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    SESSION_TTL_SECONDS: int = 7 * 24 * 60 * 60

    model_config = SettingsConfigDict(case_sensitive=True, env_file=(".env", ".env.local"), extra="ignore")

    @property
    def public_url(self) -> str:
        return self.KEYCLOAK_PUBLIC_URL or self.KEYCLOAK_URL

    @property
    def callback_url(self) -> str:
        return f"{self.BACKEND_PUBLIC_URL}/api/auth/callback"

    @property
    def frontend_origins(self) -> list[str]:
        return [url.rstrip("/") for url in (self.FRONTEND_URL, self.EPHEMERAL_FRONTEND_URL) if url]
