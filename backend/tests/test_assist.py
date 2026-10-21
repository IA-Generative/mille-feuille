import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.routers import assist as assist_router


def _fake_openai_client(
    all_ids: list[str] = (), *, chat_capable_ids: set[str] = frozenset(), completion_content: str = "réponse"
) -> SimpleNamespace:
    async def create_chat(model: str, **_kwargs):
        if model not in chat_capable_ids and _kwargs.get("max_tokens") == 1:
            # Appel de sondage (_supports_chat) : distinct de l'appel réel.
            raise RuntimeError(f"model '{model}' does not support chat completions")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=completion_content))],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=5),
        )

    models_data = [SimpleNamespace(id=i) for i in all_ids]
    return SimpleNamespace(
        models=SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(data=models_data))),
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=create_chat))),
    )


def test_complete_with_explicit_model(client, monkeypatch):
    fake_client = _fake_openai_client(completion_content="Voici un prompt.")
    monkeypatch.setattr(assist_router, "_openai_client", fake_client)

    response = client.post("/api/llm/complete", json={"prompt": "Rédige un prompt.", "model": "gpt-4o"})

    assert response.status_code == 200
    assert response.json() == {"content": "Voici un prompt."}
    call_kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o"
    assert call_kwargs["messages"] == [{"role": "user", "content": "Rédige un prompt."}]


def test_complete_falls_back_to_default_chat_model(client, monkeypatch):
    fake_client = _fake_openai_client(
        all_ids=["gpt-4o", "text-embedding-3"],
        chat_capable_ids={"gpt-4o"},
        completion_content="Réponse par défaut.",
    )
    monkeypatch.setattr(assist_router, "_openai_client", fake_client)

    with patch("app.routers.assist.redis_connector") as mock_redis:
        mock_redis.client.get.return_value = None

        response = client.post("/api/llm/complete", json={"prompt": "Rédige un prompt."})

    assert response.status_code == 200
    assert response.json() == {"content": "Réponse par défaut."}
    call_kwargs = fake_client.chat.completions.create.call_args_list[-1].kwargs
    assert call_kwargs["model"] == "gpt-4o"


def test_complete_returns_503_when_llm_hub_is_not_configured(client, monkeypatch):
    monkeypatch.setattr(assist_router, "_openai_client", None)

    response = client.post("/api/llm/complete", json={"prompt": "Rédige un prompt."})

    assert response.status_code == 503


def test_complete_returns_503_when_hub_has_no_chat_capable_model(client, monkeypatch):
    fake_client = _fake_openai_client(all_ids=["text-embedding-3"], chat_capable_ids=set())
    monkeypatch.setattr(assist_router, "_openai_client", fake_client)

    with patch("app.routers.assist.redis_connector") as mock_redis:
        mock_redis.client.get.return_value = json.dumps([])

        response = client.post("/api/llm/complete", json={"prompt": "Rédige un prompt."})

    assert response.status_code == 503
