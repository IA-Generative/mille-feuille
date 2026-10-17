from pydantic_settings import BaseSettings, SettingsConfigDict

#: Plafond de `ttl_hours` ouvert à la plateforme (7 jours), bien sous les 2 ans de l'API éphémère.
#: Le résultat est rendu dans la réponse et le run supprimé aussitôt (`DELETE_RUN_AFTER_RESULT`) :
#: le TTL ne sert plus qu'à borner la rétention si cette suppression échoue.
TTL_MAX_PLATEFORME = 168
TTL_DEFAUT_PLATEFORME = 24
#: Nombre de documents par tâche, déclaré dans le schéma (`files.maxItems`) : refusé en 422 à la soumission.
MAX_FILES_PLATEFORME = 20


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="allow")

    # RabbitMQ (AsyncTaskAPI)
    BROKER_URL: str
    IN_QUEUE_NAME: str = "mille_feuille_queue_in"
    OUT_QUEUE_NAME: str = "mille_feuille_queue_out"
    WORKER_CONCURRENCY: int = 2
    HEALTH_CHECK_HOST: str = "0.0.0.0"  # noqa: S104
    HEALTH_CHECK_PORT: int = 8084
    LOG_LEVEL: str = "INFO"
    # Classe de service déclarée dans `config/services.yaml` d'async-api : elle décide si les appels
    # `progress()` sont émis. Absente, la bibliothèque applique son défaut.
    SERVICE_CLASS: str | None = None

    # Stockage objet d'AsyncTaskAPI, où les fichiers sont déposés avant la tâche.
    AWS_ENDPOINT_URL: str
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_DEFAULT_REGION: str = "fr-par"
    AWS_S3_BUCKET_NAME: str
    AWS_S3_VERIFY: bool = True

    # API mille-feuille (l'API éphémère est appelée avec un token API : X-App-Token).
    MILLEFEUILLE_BASE_URL: str
    MILLEFEUILLE_API_TOKEN: str
    MILLEFEUILLE_REQUEST_TIMEOUT: float = 30.0

    # Garde-fous : le worker charge les fichiers en mémoire avant de les envoyer au backend
    # (contrat de service d'async-api, §5 : borner ses consommations).
    MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024
    MAX_TOTAL_SIZE_BYTES: int = 100 * 1024 * 1024
    MAX_FILES: int = MAX_FILES_PLATEFORME

    # Durée maximale d'attente de la fin d'un run, et fréquence d'interrogation.
    RUN_TIMEOUT_SECONDS: float = 900.0
    POLL_INTERVAL_SECONDS: float = 3.0
    # Supprime le résultat conservé côté mille-feuille une fois renvoyé dans le message `success`.
    DELETE_RUN_AFTER_RESULT: bool = True


settings = Settings()
