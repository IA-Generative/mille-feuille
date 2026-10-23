"""Tâches de l'index de recherche des dossiers (Qdrant) : indexation d'un document, reconstruction blue/green,
suppression. La logique est dans `app.search.service`."""

from app.celery_app import celery_app
from app.search import service


@celery_app.task(name="app.tasks.index_document")
def index_document(dossier_id: str, document_id: str) -> None:
    service.index_document(dossier_id, document_id)


@celery_app.task(name="app.tasks.remove_document_from_index")
def remove_document_from_index(dossier_id: str, document_id: str) -> None:
    service.remove_document(dossier_id, document_id)


@celery_app.task(name="app.tasks.rebuild_index")
def rebuild_index(rebuild_id: str) -> None:
    service.rebuild_index(rebuild_id)


@celery_app.task(name="app.tasks.finalize_rebuild")
def finalize_rebuild(rebuild_id: str) -> None:
    service.finalize_rebuild(rebuild_id)


@celery_app.task(name="app.tasks.rollback_rebuild")
def rollback_rebuild(rebuild_id: str) -> None:
    service.rollback_rebuild(rebuild_id)


@celery_app.task(name="app.tasks.drop_dossier_index")
def drop_dossier_index(dossier_id: str) -> None:
    service.drop_dossier_index(dossier_id)
