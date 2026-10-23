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
    # Qdrant : l'index de recherche des dossiers (un alias `dossier_<id>` par dossier). Vide = non configuré ;
    # `:memory:` sert aux tests et au développement sans service.
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    # Recherche hybride (dense + creux) fusionnée par RRF : `k` de la fusion, nombre de candidats gardés par branche
    # avant fusion, et nombre de passages renvoyés à l'agent.
    SEARCH_TOP_K: int = 5
    # Recherche BM25 en mémoire, retirée avec le passage à Qdrant.
    BM25_TOP_K: int = 5
    SEARCH_RRF_K: int = 60
    SEARCH_BRANCH_LIMIT: int = 30
    # Embeddings (API compatible OpenAI, `/embeddings`) : taille des lots envoyés au modèle.
    EMBEDDING_BATCH_SIZE: int = 32
    # Vecteur creux lexical (BM25) : saturation de la fréquence des termes, normalisation par la longueur et
    # longueur moyenne d'un passage (en termes) servant de référence.
    SPARSE_BM25_K1: float = 1.2
    SPARSE_BM25_B: float = 0.75
    SPARSE_AVG_LENGTH: float = 120.0

    model_config = SettingsConfigDict(case_sensitive=True, env_file=(".env", ".env.local"), extra="ignore")

    @property
    def celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL or DEFAULT_REDIS_URL

    @property
    def celery_result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL or DEFAULT_REDIS_URL

    @property
    def search_configured(self) -> bool:
        return bool(self.QDRANT_URL)

    @property
    def is_configured(self) -> bool:
        return bool(self.OPENAI_API_KEY and self.OPENAI_API_BASE_URL)


settings = WorkerSettings()
