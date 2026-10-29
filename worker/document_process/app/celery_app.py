from celery import Celery

from app.config import settings
from app.ocr.routing import ocr_task_queues

celery_app = Celery("document_process", broker=settings.celery_broker_url, backend=settings.celery_result_backend)

celery_app.conf.update(
    # Un document mal formé (PDF corrompu, OCR qui boucle) est tué plutôt
    # que de bloquer la queue - SIGKILL, pas une demande polie : le parsing
    # n'est pas interruptible proprement.
    task_time_limit=settings.task_time_limit,
    # Les pods d'OCR (app/ocr/) : ce worker ne fait qu'y envoyer. Celery crée la file à l'envoi avec l'exchange et la
    # clé de routage de même nom que le pod déclare - et sans `task_queues`, ce worker ne consomme que la sienne.
    task_routes={name: {"queue": queue} for name, queue in ocr_task_queues().items()},
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
)

from app import tasks  # noqa: E402,F401
