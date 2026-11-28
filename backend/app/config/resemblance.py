from pydantic_settings import BaseSettings, SettingsConfigDict


class ResemblanceSettings(BaseSettings):
    """Thèmes de ressemblance entre dossiers (#649)."""

    # Le calcul rapproche des personnes à travers tous les dossiers : désactivé tant que la finalité, la base légale,
    # la durée de conservation et les personnes autorisées ne sont pas définies.
    RESEMBLANCE_ENABLED: bool = False
    # Recalcul périodique des thèmes actifs, pour suivre les dossiers qui changent.
    RESEMBLANCE_INTERVAL_MINUTES: int = 60
    # Similarité (cosinus) en dessous de laquelle une définition d'entité n'est pas proposée. Dépend du modèle
    # d'embeddings : à régler sur les définitions réelles.
    RESEMBLANCE_SUGGESTION_MIN_SCORE: float = 0.6

    model_config = SettingsConfigDict(case_sensitive=True, env_file=(".env", ".env.local"), extra="ignore")
