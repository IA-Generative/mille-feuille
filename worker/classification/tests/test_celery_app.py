from app.celery_app import celery_app


def test_celery_app_listens_on_its_own_queue() -> None:
    assert celery_app.main == "classification"
    assert celery_app.conf.task_default_queue == "classification"


def test_classification_task_is_registered() -> None:
    celery_app.loader.import_default_modules()
    assert "app.tasks.classify_dossier" in celery_app.tasks
