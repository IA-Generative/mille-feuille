from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_KEY_LENGTH = 16


class EphemeralSettings(BaseSettings):
    # Clé d'API statique donnant accès à /api/ephemeral/* (en-tête `X-App-Token: <clé>` ou
    # `Authorization: Bearer <clé>`), sans session Keycloak ni jeton créé en base. Vide (défaut) : désactivée.
    # Une requête authentifiée par cette clé est toujours non persistante (`persist=true` est refusé) et ne peut
    # lancer que les analyses éphémères qu'elle a elle-même créées.
    EPHEMERAL_API_KEY: str = ""

    model_config = SettingsConfigDict(case_sensitive=True, env_file=(".env", ".env.local"), extra="ignore")

    @field_validator("EPHEMERAL_API_KEY")
    @classmethod
    def _key_must_be_long_enough(cls, value: str) -> str:
        value = value.strip()
        if value and len(value) < MIN_KEY_LENGTH:
            raise ValueError(f"EPHEMERAL_API_KEY doit faire au moins {MIN_KEY_LENGTH} caractères (ou être vide).")
        return value
