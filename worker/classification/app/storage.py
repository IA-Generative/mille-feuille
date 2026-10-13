import boto3

from app.config import settings


class RustFsStorage:
    """RustFS est compatible S3 - un client boto3 classique lui parle
    directement, pas besoin d'un SDK dédié à RustFS. Même implémentation que
    worker/document_process/app/storage.py : les deux workers accèdent au
    même bucket (captures de pages, documents uploadés)."""

    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        self._bucket = settings.AWS_S3_BUCKET_NAME

    def get_object(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()


storage = RustFsStorage()
