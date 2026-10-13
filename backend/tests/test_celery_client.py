import pytest

from app import celery_client


@pytest.mark.parametrize(
    ("dispatch", "task", "queue"),
    [
        (celery_client.dispatch_classification, "app.tasks.classify_dossier", "classification"),
        (celery_client.dispatch_entity_extraction, "app.tasks.extract_dossier_entities", "entity_extraction"),
        (celery_client.dispatch_agent_execution, "app.tasks.run_agents", "agent_execution"),
    ],
)
def test_dispatch_targets_the_dedicated_queue(monkeypatch: pytest.MonkeyPatch, dispatch, task: str, queue: str) -> None:
    sent: list[tuple[str, dict]] = []

    def send_task(name: str, **kwargs):
        sent.append((name, kwargs))
        return type("Result", (), {"id": "task-1"})()

    monkeypatch.setattr(celery_client.celery_client, "send_task", send_task)

    assert dispatch("dossier-1") == "task-1"
    assert sent == [(task, {"args": ["dossier-1"], "queue": queue})]
