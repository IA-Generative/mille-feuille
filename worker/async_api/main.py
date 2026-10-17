import asyncio

from loguru import logger
from mic_worker import S3Client
from mic_worker.manifeste import charger_voisin
from mic_worker.typed import HealthCheckConfig, Infinite
from mic_worker.worker import AsyncWorkerRunner
from millefeuille_ephemeral import EphemeralClient

import src.logger  # noqa: F401 — side-effect: configure logging
from src.config import settings
from src.task import AnalyzeTask


def build_s3_client() -> S3Client:
    return S3Client(
        endpoint_url=settings.AWS_ENDPOINT_URL,
        access_key=settings.AWS_ACCESS_KEY_ID,
        secret_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_DEFAULT_REGION,
        bucket_name=settings.AWS_S3_BUCKET_NAME,
        verify=settings.AWS_S3_VERIFY,
    )


def build_client(timeout: float = settings.MILLEFEUILLE_REQUEST_TIMEOUT) -> EphemeralClient:
    return EphemeralClient(
        settings.MILLEFEUILLE_BASE_URL,
        api_token=settings.MILLEFEUILLE_API_TOKEN,
        timeout=timeout,
    )


async def main() -> None:
    # Contrat déclaré par le module, lu au démarrage : un manifeste invalide empêche de démarrer.
    manifeste = charger_voisin(__file__)
    logger.info(f"Contrat : {manifeste.nom} — {manifeste.titre} (classe {manifeste.classe})")

    s3_client = build_s3_client()
    client = build_client()
    # Le dépôt multipart porte les fichiers : son délai est le seul à devoir couvrir MAX_TOTAL_SIZE_BYTES.
    client_depot = build_client(timeout=settings.MILLEFEUILLE_UPLOAD_TIMEOUT)

    runner = AsyncWorkerRunner(
        amqp_url=settings.BROKER_URL,
        amqp_in_queue=settings.IN_QUEUE_NAME,
        amqp_out_queue=settings.OUT_QUEUE_NAME,
        task_provider=lambda: AnalyzeTask(
            s3_client=s3_client,
            client=client,
            client_depot=client_depot,
            max_file_size=settings.MAX_FILE_SIZE_BYTES,
            max_total_size=settings.MAX_TOTAL_SIZE_BYTES,
            max_files=settings.MAX_FILES,
            run_timeout=settings.RUN_TIMEOUT_SECONDS,
            poll_interval=settings.POLL_INTERVAL_SECONDS,
            delete_run_after_result=settings.DELETE_RUN_AFTER_RESULT,
        ),
        worker_mode=Infinite(concurrency=settings.WORKER_CONCURRENCY),
        # `/ready` n'éprouve que le stockage objet, local au socle. Le backend mille-feuille n'est pas
        # sondé : sa disponibilité se voit à l'échec des tâches (même choix que les autres modules).
        health_check_config=HealthCheckConfig(
            host=settings.HEALTH_CHECK_HOST,
            port=settings.HEALTH_CHECK_PORT,
            sondes={"object_storage": s3_client.verifier_acces},
        ),
        classe_de_service=settings.SERVICE_CLASS,
    )
    try:
        await runner.start()
    finally:
        client.close()
        client_depot.close()
    logger.info("mille-feuille async-api worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
