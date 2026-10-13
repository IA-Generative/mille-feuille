from app.celery_app import celery_app


def test_celery_app_listens_on_its_own_queue() -> None:
    assert celery_app.main == "extraction"
    assert celery_app.conf.task_default_queue == "entity_extraction"


def test_extraction_task_is_registered() -> None:
    celery_app.loader.import_default_modules()
    assert "app.tasks.extract_dossier_entities" in celery_app.tasks
