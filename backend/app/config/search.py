from pydantic_settings import BaseSettings, SettingsConfigDict


class SearchSettings(BaseSettings):
    """Valeurs par défaut de la recherche dans les dossiers : elles s'appliquent quand une analyse ne choisit pas
    elle-même ses modèles (voir app.services.search.settings)."""

    # Modèle d'embeddings servi par le hub (`/embeddings`). Vide : l'analyse doit en choisir un.
    SEARCH_EMBEDDING_MODEL: str = ""
    # Modèle qui découpe les pages quand la stratégie est « ia ». Vide : l'analyse doit en choisir un.
    SEARCH_CHUNK_MODEL: str = ""

    # Reconstructions d'index qui tournent en même temps pour une analyse (les autres attendent leur tour).
    SEARCH_MAX_PARALLEL_REBUILDS: int = 3

    # Qdrant : l'index de recherche des dossiers (un alias `dossier_<id>` par dossier). Vide = non configuré ;
    # `:memory:` sert aux tests et au développement sans service.
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    # Recherche hybride (dense + creux) fusionnée par RRF : `k` de la fusion, nombre de candidats gardés par branche
    # avant fusion, et nombre de passages renvoyés à l'agent.
    SEARCH_TOP_K: int = 5
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
    def qdrant_configured(self) -> bool:
        return bool(self.QDRANT_URL)
