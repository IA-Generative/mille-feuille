"""Déclaration de la consommation de tokens : seuls des compteurs partent vers le backend."""

import httpx
import pytest

from app import usage


@pytest.fixture
def posted(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []

    def fake_post(url: str, **kwargs) -> httpx.Response:
        calls.append({"url": url, **kwargs})
        return httpx.Response(204, request=httpx.Request("POST", url))

    monkeypatch.setattr(usage.httpx, "post", fake_post)
    return calls


def _chat_response(status: int = 200, path: str = "/v1/chat/completions") -> httpx.Response:
    return httpx.Response(
        status,
        json={"model": "m1", "usage": {"prompt_tokens": 11, "completion_tokens": 4}, "choices": []},
        request=httpx.Request("POST", f"http://hub{path}"),
    )


def test_a_completion_is_reported_with_its_task_and_person(posted: list[dict]) -> None:
    usage.bind("run_chat", user_id="u1", dossier_id="d1")

    usage._report(_chat_response())

    assert len(posted) == 1
    assert posted[0]["json"] == {
        "step": "run_chat",
        "model": "m1",
        "kind": "chat",
        "input_tokens": 11,
        "output_tokens": 4,
        "user_id": "u1",
        "dossier_id": "d1",
    }
    assert posted[0]["url"].endswith("/api/internal/usage")


def test_other_calls_and_failed_calls_are_not_reported(posted: list[dict]) -> None:
    usage._report(_chat_response(path="/v1/models"))
    usage._report(_chat_response(status=500))

    assert posted == []


def test_a_backend_failure_never_breaks_the_llm_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_post(*_args, **_kwargs):
        raise httpx.ConnectError("backend injoignable")

    monkeypatch.setattr(usage.httpx, "post", broken_post)

    usage._report(_chat_response())
