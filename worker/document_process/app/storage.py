import boto3

from app.config import settings


class RustFsStorage:
    """RustFS est compatible S3 - un client boto3 classique lui parle
    directement, pas besoin d'un SDK dédié à RustFS."""

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

    def put_object(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        # Le bucket existe déjà : un document ne peut être traité que s'il a
        # d'abord été uploadé par le backend (voir S3Connector.upload côté
        # backend, qui le crée si besoin).
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def delete_objects(self, keys: list[str]) -> None:
        """Supprime des objets (les images temporaires de pages confiées aux pods d'OCR)."""
        for start in range(0, len(keys), 1000):
            self._client.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": [{"Key": key} for key in keys[start : start + 1000]], "Quiet": True},
            )


storage = RustFsStorage()
