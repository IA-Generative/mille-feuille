from celery import Celery

from app.config import settings

# `include` : le module qui définit la @celery_app.task n'est importé nulle part ailleurs, sans lui le worker
# démarre avec un registre de tâches vide et rejette tout message reçu comme « unregistered task ».
celery_app = Celery(
    "classification",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.classification"],
)
# File dédiée : le backend y dépose la tâche (voir backend/app/celery_client.py).
celery_app.conf.task_default_queue = "classification"
