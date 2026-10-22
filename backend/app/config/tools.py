from pydantic_settings import BaseSettings, SettingsConfigDict


class ToolSettings(BaseSettings):
    # Domaines autorisés pour les serveurs MCP ajoutés par les utilisateurs, séparés par des virgules (un domaine
    # autorise aussi ses sous-domaines). Vide (défaut) : tout domaine public est accepté ; les adresses privées,
    # locales et de métadonnées cloud restent toujours refusées.
    TOOL_SERVER_ALLOWED_DOMAINS: str = ""

    # Développement seulement : accepte http et les adresses privées ou locales (un serveur MCP lancé en local).
    TOOL_SERVER_ALLOW_INSECURE: bool = False

    # Durée maximale d'une découverte des tools d'un serveur (`tools/list`).
    TOOL_DISCOVERY_TIMEOUT_SECONDS: float = 10.0

    model_config = SettingsConfigDict(case_sensitive=True, env_file=(".env", ".env.local"), extra="ignore")

    @property
    def allowed_domains(self) -> list[str]:
        return [domain.strip().lower() for domain in self.TOOL_SERVER_ALLOWED_DOMAINS.split(",") if domain.strip()]
