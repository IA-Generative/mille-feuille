from pydantic_settings import BaseSettings, SettingsConfigDict


class VisionSettings(BaseSettings):
    # Comme worker/document_process : en Kubernetes, le secret `millefeuille-redis` fournit `REDIS_URL` ; à défaut
    # de `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` (docker-compose), c'est lui qui sert.
    REDIS_URL: str = ""
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""
    # Shared with the extraction worker (worker/document_process/app/config.py): the queue this pod consumes.
    VISION_QUEUE_NAME: str = "document_vision"

    AWS_ENDPOINT_URL: str = "http://localhost:9000"
    AWS_ACCESS_KEY_ID: str = "rustfsadmin"
    AWS_SECRET_ACCESS_KEY: str = "rustfsadmin"
    AWS_S3_BUCKET_NAME: str = "mille-feuille"
    STORAGE_CONNECT_TIMEOUT_SECONDS: int = 10
    STORAGE_READ_TIMEOUT_SECONDS: int = 60

    # Hub LLM (API compatible OpenAI) : mêmes variables que worker/classification, dont `VLM_MODEL`, le modèle qui
    # lit les images. Le pod n'embarque aucun modèle : il montre chaque recadrage au VLM du hub.
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE_URL: str = ""
    VLM_MODEL: str = "pixtral-12b-2409"
    HUB_TIMEOUT_SECONDS: int = 120
    HUB_MAX_TOKENS: int = 300
    # Un peu de la page autour de la région, sinon le bord d'une image coupée au plus près est perdu.
    VISION_CROP_MARGIN_PIXELS: int = 8
    # Les régions d'une page, au plus - le worker d'extraction les plafonne plus bas ; c'est la garde du pod.
    VISION_MAX_REGIONS: int = 50

    # A page's task: an exception raised in it past the limit, never a kill.
    VISION_TASK_SOFT_TIME_LIMIT_SECONDS: int = 5 * 60
    # Above the soft limit, or a task still running would be handed to another worker.
    BROKER_VISIBILITY_TIMEOUT_SECONDS: int = 30 * 60

    @property
    def celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL or "redis://localhost:6379/0"

    @property
    def celery_result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL or "redis://localhost:6379/0"

    model_config = SettingsConfigDict(case_sensitive=True, env_file=(".env", ".env.local"), extra="ignore")


settings = VisionSettings()
