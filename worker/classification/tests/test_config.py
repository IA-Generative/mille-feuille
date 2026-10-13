"""Tests de la configuration du worker : d'où viennent le broker et le backend de résultats Celery."""

import pytest

from app.config import DEFAULT_REDIS_URL, WorkerSettings


def settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> WorkerSettings:
    for name in ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return WorkerSettings(_env_file=None)


def test_without_any_variable_the_worker_targets_local_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    config = settings(monkeypatch)
    assert config.celery_broker_url == config.celery_result_backend == DEFAULT_REDIS_URL


def test_the_redis_secret_of_kubernetes_serves_as_broker_and_results(monkeypatch: pytest.MonkeyPatch) -> None:
    config = settings(monkeypatch, REDIS_URL="redis://:motdepasse@millefeuille-redis:6379/0")
    assert config.celery_broker_url == "redis://:motdepasse@millefeuille-redis:6379/0"
    assert config.celery_result_backend == "redis://:motdepasse@millefeuille-redis:6379/0"


def test_explicit_celery_urls_win_over_the_redis_url(monkeypatch: pytest.MonkeyPatch) -> None:
    config = settings(
        monkeypatch,
        REDIS_URL="redis://secret:6379/0",
        CELERY_BROKER_URL="redis://broker:6379/1",
        CELERY_RESULT_BACKEND="redis://results:6379/2",
    )
    assert config.celery_broker_url == "redis://broker:6379/1"
    assert config.celery_result_backend == "redis://results:6379/2"
