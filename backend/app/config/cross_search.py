from pydantic_settings import BaseSettings, SettingsConfigDict


class CrossSearchSettings(BaseSettings):
    """Recherche à travers les dossiers (épique #637)."""

    # Annoncer, par thème, le nombre de dossiers non accessibles liés aux résultats (#641, #647). Désactivé par
    # défaut : un simple nombre peut apprendre qu'une personne a un dossier ailleurs.
    SEARCH_HIDDEN_LINKS_ENABLED: bool = False
    # En dessous de ce nombre de dossiers dans un thème, rien n'est annoncé.
    SEARCH_HIDDEN_LINKS_MIN: int = 1

    model_config = SettingsConfigDict(case_sensitive=True, env_file=(".env", ".env.local"), extra="ignore")
