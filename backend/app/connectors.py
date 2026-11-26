from datetime import UTC, datetime, timedelta

import boto3
import redis
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import RedisSettings, StorageSettings, TlsSettings
from app.db import engine as db_engine
from app.schemas.health import Health


class RedisConnector:
    def __init__(self, url: str) -> None:
        self.client = redis.Redis.from_url(url, decode_responses=True)

    def get_health(self) -> Health:
        try:
            self.client.ping()
            return Health(name="redis", status="healthy")
        except redis.RedisError as error:
            return Health(name="redis", status="unhealthy", extras={"error": str(error)})


class DatabaseConnector:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def get_health(self) -> Health:
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return Health(name="postgres", status="healthy")
        except Exception as error:
            return Health(name="postgres", status="unhealthy", extras={"error": str(error)})


class S3Connector:
    """RustFS en local/dev, un bucket S3 réel en prod (voir StorageSettings) -
    même client boto3 dans les deux cas, seul endpoint_url change."""

    def __init__(self, settings: StorageSettings) -> None:
        self.bucket = settings.AWS_S3_BUCKET_NAME
        client_cert = (
            (settings.S3_MTLS_CERT_PATH, settings.S3_MTLS_KEY_PATH)
            if settings.S3_MTLS_CERT_PATH and settings.S3_MTLS_KEY_PATH
            else None
        )
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_DEFAULT_REGION,
            verify=TlsSettings().verify,
            config=BotoConfig(
                connect_timeout=2, read_timeout=2, retries={"max_attempts": 0}, client_cert=client_cert
            ),
        )

    def get_health(self) -> Health:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return Health(name="s3", status="healthy")
        except (BotoCoreError, ClientError) as error:
            return Health(name="s3", status="unhealthy", extras={"error": str(error)})

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self.client.create_bucket(Bucket=self.bucket)
        except self.client.exceptions.BucketAlreadyOwnedByYou:
            pass
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def download(self, key: str) -> tuple[bytes, str]:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        content_type = response.get("ContentType") or "application/octet-stream"
        return response["Body"].read(), content_type

    def delete_prefix(self, prefix: str, *, older_than: timedelta | None = None, keep: set[str] = frozenset()) -> int:
        """Supprime les objets d'un préfixe (éventuellement seulement les plus anciens que ``older_than``, et jamais
        ceux de ``keep``) et renvoie leur nombre. Comme ``delete``, avale les erreurs de connectivité : un nettoyage
        ne bloque rien."""
        deleted = 0
        try:
            cutoff = datetime.now(UTC) - older_than if older_than else None
            paginator = self.client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    if obj["Key"] in keep or (cutoff is not None and obj["LastModified"] > cutoff):
                        continue
                    self.client.delete_object(Bucket=self.bucket, Key=obj["Key"])
                    deleted += 1
        except (BotoCoreError, ClientError):
            pass
        return deleted

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except (BotoCoreError, ClientError):
            return False

    def delete(self, key: str) -> None:
        # delete_object est idempotent côté S3 (pas d'erreur si la clé
        # n'existe déjà plus) : rien à faire de spécial pour ce cas. On
        # avale seulement les erreurs de connectivité/permission, pour
        # qu'un objet inaccessible ne bloque jamais la suppression DB qui
        # suit (voir DossierRepository.delete_dossier).
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError):
            pass


redis_settings = RedisSettings()
redis_connector = RedisConnector(redis_settings.REDIS_URL)
db_connector = DatabaseConnector(db_engine)
storage_settings = StorageSettings()
s3_connector = S3Connector(storage_settings)
