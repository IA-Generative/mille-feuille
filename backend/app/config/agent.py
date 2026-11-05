from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    # Modèle texte pour les agents, le chat, les résumés et les propositions.
    LLM_MODEL: str = "llama-3.3-70b-instruct"
    # Modèle du planificateur du chat (un petit modèle suffit : il ne fait que décider). Vide : le modèle du chat.
    CHAT_PLAN_MODEL: str = ""
    # Mode auto : le modèle est choisi selon la difficulté de la demande (niveau de chaque modèle, table llm_models).
    # Désactivé, le premier modèle de complétion de la table fait tout. Sans modèle en table : LLM_MODEL.
    LLM_AUTO_MODE: bool = False
    # Nombre maximum d'itérations du graphe LangGraph (pour éviter les boucles infinies).
    AGENT_MAX_ITERATIONS: int = 10
    # Travaux de l'agent (agents d'analyse, chat, résumés...) menés en même temps dans un process du backend : les
    # suivants attendent leur tour.
    MAX_CONCURRENT_JOBS: int = 8
    # Génération des valeurs de champs d'un document (issue #141) : budget de jetons estimés du contexte
    # (éléments de l'analyse et notes) d'un appel, nombre de champs par appel, et taille maximale d'un
    # élément ou d'une note avant coupe. Des réglages à ajuster sur de vrais dossiers.
    GENERATION_MAX_CONTEXT_TOKENS: int = 12000
    GENERATION_FIELDS_PER_CALL: int = 10
    GENERATION_MAX_ITEM_CHARS: int = 1500

    model_config = SettingsConfigDict(case_sensitive=True, env_file=(".env", ".env.local"), extra="ignore")
