from pydantic_settings import BaseSettings, SettingsConfigDict


class SearchSettings(BaseSettings):
    """Valeurs par défaut de la recherche dans les dossiers : elles s'appliquent quand une analyse ne choisit pas
    elle-même ses modèles (voir app.services.search.settings)."""

    # Modèle d'embeddings servi par le hub (`/embeddings`). Vide : l'analyse doit en choisir un.
    SEARCH_EMBEDDING_MODEL: str = ""
    # Modèle qui découpe les pages quand la stratégie est « ia ». Vide : l'analyse doit en choisir un.
    SEARCH_CHUNK_MODEL: str = ""

    model_config = SettingsConfigDict(case_sensitive=True, env_file=(".env", ".env.local"), extra="ignore")
