from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_S3_ENDPOINT_URL = "http://localhost:9000"


class WorkerSettings(BaseSettings):
    # Broker et résultats Celery. En Kubernetes, le secret `millefeuille-redis` fournit `REDIS_URL` (avec le mot de
    # passe) : à défaut de `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` (docker-compose), c'est lui qui sert.
    REDIS_URL: str = ""
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    # RustFS en local/dev, un bucket S3 réel en prod. Variables standard AWS : `AWS_ENDPOINT_URL` est défini par le
    # chart en Kubernetes (le secret `millefeuille-s3` peut aussi le fournir, parfois sans schéma).
    AWS_ENDPOINT_URL: str = ""
    AWS_ACCESS_KEY_ID: str = "rustfsadmin"
    AWS_SECRET_ACCESS_KEY: str = "rustfsadmin"
    AWS_S3_BUCKET_NAME: str = "mille-feuille"

    # LibreOffice en ligne de commande (conversion en PDF).
    SOFFICE_BINARY: str = "soffice"
    # Délai maximal d'une conversion : au-delà, le processus LibreOffice (et ses enfants) est tué.
    SOFFICE_TIMEOUT_SECONDS: int = 120
    # Fontconfig : sert à savoir si une police du modèle est installée dans l'image (issue #148).
    FC_MATCH_BINARY: str = "fc-match"

    # Vérification des certificats TLS des appels sortants (backend, LLM, S3). Activée par défaut ;
    # `SSL_CA_BUNDLE` (fichier PEM) ajoute une autorité interne ; `SSL_VERIFY=false` la désactive :
    # dépannage uniquement, jamais en production.
    SSL_VERIFY: bool = True
    SSL_CA_BUNDLE: str = ""

    model_config = SettingsConfigDict(case_sensitive=True, env_file=(".env", ".env.local"), extra="ignore")

    @property
    def ssl_verify(self) -> bool | str:
        """Paramètre `verify` de httpx et boto3 : `False`, le chemin d'une CA, ou `True`."""
        if not self.SSL_VERIFY:
            return False
        return self.SSL_CA_BUNDLE or True

    @property
    def celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL or DEFAULT_REDIS_URL

    @property
    def celery_result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL or DEFAULT_REDIS_URL

    @property
    def s3_endpoint_url(self) -> str:
        """Endpoint S3 avec son schéma : boto3 refuse un hôte nu (`s3.fr-par.scw.cloud`)."""
        url = self.AWS_ENDPOINT_URL or DEFAULT_S3_ENDPOINT_URL
        return url if "://" in url else f"https://{url}"


settings = WorkerSettings()
