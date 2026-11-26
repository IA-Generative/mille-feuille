from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageSettings(BaseSettings):
    # RustFS en local/dev (docker-compose), un bucket S3 réel en prod : même
    # API S3, seul l'endpoint change.
    AWS_ENDPOINT_URL: str = "http://localhost:9000"
    AWS_ACCESS_KEY_ID: str = "rustfsadmin"
    AWS_SECRET_ACCESS_KEY: str = "rustfsadmin"
    AWS_S3_BUCKET_NAME: str = "mille-feuille"
    AWS_DEFAULT_REGION: str = "us-east-1"
    # mTLS : chemins du certificat et de la clé client présentés au S3 (PEM). Vides = pas de certificat client.
    S3_MTLS_CERT_PATH: str = ""
    S3_MTLS_KEY_PATH: str = ""

    model_config = SettingsConfigDict(case_sensitive=True, env_file=(".env", ".env.local"), extra="ignore")
