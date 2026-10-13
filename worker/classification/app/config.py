from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_REDIS_URL = "redis://localhost:6379/0"


class WorkerSettings(BaseSettings):
    # Broker et résultats Celery. En Kubernetes, le secret `millefeuille-redis` fournit `REDIS_URL` (avec le mot de
    # passe) : à défaut de `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` (docker-compose), c'est lui qui sert.
    REDIS_URL: str = ""
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    BACKEND_INTERNAL_URL: str = "http://localhost:8000"
    INTERNAL_WORKER_TOKEN: str = ""

    # RustFS en local/dev, un bucket S3 réel en prod (mêmes noms de variables que le backend, voir StorageSettings) :
    # les captures de pages y sont lues.
    AWS_ENDPOINT_URL: str = "http://localhost:9000"
    AWS_ACCESS_KEY_ID: str = "rustfsadmin"
    AWS_SECRET_ACCESS_KEY: str = "rustfsadmin"
    AWS_S3_BUCKET_NAME: str = "mille-feuille"

    # Hub LLM (compatible API OpenAI) - mêmes variables que côté backend (voir app.config.llm.LlmSettings).
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE_URL: str = ""
    # Modèle vision pour décrire la capture de chaque page (VLM).
    VLM_MODEL: str = "pixtral-12b-2409"
    # Modèle texte pour la classification.
    LLM_MODEL: str = "llama-3.3-70b-instruct"

    # Classification visuelle (CLIP, CPU) : en plus de la classification textuelle, chaque page est classée sur sa
    # capture. `CLIP_MODEL` est le nom d'un modèle Hugging Face, embarqué dans l'image (voir Dockerfile) : le worker
    # ne télécharge rien au démarrage.
    CLIP_ENABLED: bool = True
    CLIP_MODEL: str = "openai/clip-vit-base-patch32"
    CLIP_NUM_THREADS: int = 2
    # Multi-label : probabilité minimale (softmax sur les labels) pour retenir un label en plus du meilleur.
    CLIP_MULTI_LABEL_THRESHOLD: float = 0.25

    model_config = SettingsConfigDict(case_sensitive=True, env_file=(".env", ".env.local"), extra="ignore")

    @property
    def celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL or DEFAULT_REDIS_URL

    @property
    def celery_result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL or DEFAULT_REDIS_URL

    @property
    def is_configured(self) -> bool:
        return bool(self.OPENAI_API_KEY and self.OPENAI_API_BASE_URL)


settings = WorkerSettings()
