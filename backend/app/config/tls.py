from pydantic_settings import BaseSettings, SettingsConfigDict


class TlsSettings(BaseSettings):
    """Vérification des certificats TLS des appels sortants du backend (LLM, S3, Keycloak, outils MCP, connaissances).

    Activée par défaut. `SSL_CA_BUNDLE` (chemin d'un fichier PEM) ajoute une autorité interne ; `SSL_VERIFY=false`
    désactive la vérification : à réserver au dépannage, jamais en production.
    """

    SSL_VERIFY: bool = True
    SSL_CA_BUNDLE: str = ""

    model_config = SettingsConfigDict(case_sensitive=True, env_file=(".env", ".env.local"), extra="ignore")

    @property
    def verify(self) -> bool | str:
        """Valeur du paramètre `verify` de httpx, boto3 et python-keycloak : `False`, un chemin de CA, ou `True`."""
        if not self.SSL_VERIFY:
            return False
        return self.SSL_CA_BUNDLE or True
