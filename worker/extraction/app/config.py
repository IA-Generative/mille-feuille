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

    # Hub LLM (compatible API OpenAI) - mêmes variables que côté backend (voir app.config.llm.LlmSettings).
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE_URL: str = ""
    # Modèle texte pour l'extraction d'entités.
    LLM_MODEL: str = "llama-3.3-70b-instruct"

    # Extraction GLiNER2.5 (CPU) : en plus du LLM, chaque document est passé dans GLiNER, qui reçoit les définitions des
    # entités comme descriptions. `GLINER_MODEL` est un modèle Hugging Face embarqué dans l'image (voir Dockerfile) :
    # le worker ne télécharge rien au démarrage. `multi` pour du texte français ; `base` est anglais seulement.
    GLINER_ENABLED: bool = True
    GLINER_MODEL: str = "fastino/gliner2.5-multi-v1"
    GLINER_NUM_THREADS: int = 2
    # Confiance minimale (0 à 1) d'une entité GLiNER pour être retenue.
    GLINER_THRESHOLD: float = 0.5
    # Taille de batch pour l'extraction d'entités : nombre de pages
    # envoyées en un seul appel LLM (compromis contexte/coût).
    # (Mode « legacy » uniquement, voir EXTRACTION_MODE.)
    EXTRACTION_BATCH_SIZE: int = 5

    # Extraction d'entités (issue #126) :
    # - "by_document" : un appel par (lot de pages d'un même document × groupe
    #   de définitions) ; les lots sont définis par un budget de jetons.
    # - "legacy" : l'ancien comportement (lots de EXTRACTION_BATCH_SIZE pages
    #   sur tout le dossier, toutes les définitions dans un seul appel), à
    #   garder le temps de valider le nouveau découpage sur de vrais dossiers.
    EXTRACTION_MODE: str = "by_document"
    # Budget total d'un appel (texte des pages + définitions + prompt + réponse),
    # en jetons estimés (un jeton ~ 4 caractères).
    EXTRACTION_MAX_TOKENS: int = 8000
    # Part du budget réservée à la réponse du LLM.
    EXTRACTION_RESERVED_OUTPUT_TOKENS: int = 1500
    # Pages communes entre deux lots consécutifs d'un document (pour ne pas
    # couper une entité qui s'étend sur deux lots).
    EXTRACTION_OVERLAP_PAGES: int = 1
    # Taille des groupes de définitions d'entités (0 : un seul groupe).
    EXTRACTION_DEFINITIONS_PER_GROUP: int = 8

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
