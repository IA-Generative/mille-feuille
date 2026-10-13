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

    # Hub LLM (compatible API OpenAI) - mêmes variables que côté backend
    # (voir app.config.llm.LlmSettings). Le worker en a besoin pour parler
    # au VLM (description d'image) et au LLM (classification/extraction en
    # structured output).
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE_URL: str = ""
    # Modèle texte pour les agents, le chat, les résumés et les propositions.
    LLM_MODEL: str = "llama-3.3-70b-instruct"
    # Génération des valeurs de champs d'un document (issue #141) : budget de jetons estimés du contexte
    # (éléments de l'analyse et notes) d'un appel, nombre de champs par appel, et taille maximale d'un
    # élément ou d'une note avant coupe. Des réglages à ajuster sur de vrais dossiers.
    GENERATION_MAX_CONTEXT_TOKENS: int = 12000
    GENERATION_FIELDS_PER_CALL: int = 10
    GENERATION_MAX_ITEM_CHARS: int = 1500

    # Nombre maximum d'itérations du graphe LangGraph (pour éviter les
    # boucles infinies).
    AGENT_MAX_ITERATIONS: int = 10
    # Nombre de résultats retournés par la recherche BM25.
    BM25_TOP_K: int = 5

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
