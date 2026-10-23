import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.routers import models as models_router


def _fake_openai_client(all_ids: list[str], *, chat_capable_ids: set[str] = frozenset()) -> SimpleNamespace:
    async def create_chat(model: str, **_kwargs):
        if model not in chat_capable_ids:
            raise RuntimeError(f"model '{model}' does not support chat completions")
        return SimpleNamespace()

    models_data = [SimpleNamespace(id=i) for i in all_ids]
    return SimpleNamespace(
        models=SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(data=models_data))),
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=create_chat))),
    )


def test_list_models_discovers_and_caches_chat_capable_models(client, monkeypatch):
    fake_client = _fake_openai_client(
        all_ids=["gpt-4o", "mistral-small", "text-embedding-3"],
        chat_capable_ids={"gpt-4o", "mistral-small"},
    )
    monkeypatch.setattr(models_router, "_openai_client", fake_client)

    with patch("app.routers.models.redis_connector") as mock_redis:
        mock_redis.client.get.return_value = None

        response = client.get("/api/models")

    assert response.status_code == 200
    model_ids = [m["id"] for m in response.json()["models"]]
    assert model_ids == ["gpt-4o", "mistral-small"]

    cached_key, cached_value = mock_redis.client.set.call_args[0]
    assert cached_key == models_router._CHAT_MODELS_CACHE_KEY
    assert json.loads(cached_value) == ["gpt-4o", "mistral-small"]


def test_list_models_uses_cache_without_calling_the_hub(client, monkeypatch):
    fake_client = _fake_openai_client(all_ids=[])
    monkeypatch.setattr(models_router, "_openai_client", fake_client)

    with patch("app.routers.models.redis_connector") as mock_redis:
        mock_redis.client.get.return_value = json.dumps(["cached-model"])

        response = client.get("/api/models")

    assert response.status_code == 200
    assert [m["id"] for m in response.json()["models"]] == ["cached-model"]
    fake_client.models.list.assert_not_called()


def test_list_models_returns_503_when_llm_hub_is_not_configured(client, monkeypatch):
    monkeypatch.setattr(models_router, "_openai_client", None)

    response = client.get("/api/models")

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# POST /api/models/refresh
# ---------------------------------------------------------------------------


def test_refresh_models_reprobes_and_updates_cache(client, monkeypatch):
    fake_client = _fake_openai_client(
        all_ids=["gpt-4o", "mistral-small", "text-embedding-3"],
        chat_capable_ids={"gpt-4o", "mistral-small"},
    )
    monkeypatch.setattr(models_router, "_openai_client", fake_client)

    with patch("app.routers.models.redis_connector") as mock_redis:
        mock_redis.client.get.return_value = json.dumps(["stale-model"])

        response = client.post("/api/models/refresh")

    assert response.status_code == 200
    model_ids = [m["id"] for m in response.json()["models"]]
    assert model_ids == ["gpt-4o", "mistral-small"]

    # Le cache doit avoir été réécrit avec la fraîche liste, même s'il
    # existait déjà (refresh ignore le cache contrairement à GET).
    cached_key, cached_value = mock_redis.client.set.call_args[0]
    assert cached_key == models_router._CHAT_MODELS_CACHE_KEY
    assert json.loads(cached_value) == ["gpt-4o", "mistral-small"]


def test_refresh_models_ignores_existing_cache(client, monkeypatch):
    """Contrairement à GET /models, POST /refresh doit *toujours* re-prober
    le hub même si le cache existe."""
    fake_client = _fake_openai_client(
        all_ids=["gpt-4o"],
        chat_capable_ids={"gpt-4o"},
    )
    monkeypatch.setattr(models_router, "_openai_client", fake_client)

    with patch("app.routers.models.redis_connector") as mock_redis:
        mock_redis.client.get.return_value = json.dumps(["stale-model"])

        response = client.post("/api/models/refresh")

    assert response.status_code == 200
    # Le hub a bien été interrogé malgré le cache présent.
    fake_client.models.list.assert_called_once()


def test_refresh_models_returns_503_when_llm_hub_is_not_configured(client, monkeypatch):
    monkeypatch.setattr(models_router, "_openai_client", None)

    response = client.post("/api/models/refresh")

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# DELETE /api/models/cache
# ---------------------------------------------------------------------------


def test_clear_cache_deletes_redis_key(client, monkeypatch):
    with patch("app.routers.models.redis_connector") as mock_redis:
        response = client.delete("/api/models/cache")

    assert response.status_code == 200
    assert response.json() == {"cleared": True}
    mock_redis.client.delete.assert_called_once_with(models_router._CHAT_MODELS_CACHE_KEY)


def test_clear_cache_then_list_reprobes(client, monkeypatch):
    """Après un DELETE /cache, le GET /models suivant doit re-prober le hub
    car le cache a été invalidé."""
    fake_client = _fake_openai_client(
        all_ids=["gpt-4o"],
        chat_capable_ids={"gpt-4o"},
    )
    monkeypatch.setattr(models_router, "_openai_client", fake_client)

    with patch("app.routers.models.redis_connector") as mock_redis:
        # Premier GET : cache vide, remplit le cache.
        mock_redis.client.get.return_value = None
        client.get("/api/models")
        fake_client.models.list.reset_mock()

        # On vide le cache.
        client.delete("/api/models/cache")

        # Second GET : doit re-prober (cache toujours manquant).
        response = client.get("/api/models")

    assert response.status_code == 200
    fake_client.models.list.assert_called_once()


def _fake_embedding_client(dimensions: dict[str, int], all_ids: list[str]) -> SimpleNamespace:
    async def create_embedding(model: str, **_kwargs):
        if model not in dimensions:
            raise RuntimeError(f"model '{model}' does not support embeddings")
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.0] * dimensions[model])])

    return SimpleNamespace(
        models=SimpleNamespace(
            list=AsyncMock(return_value=SimpleNamespace(data=[SimpleNamespace(id=i) for i in all_ids]))
        ),
        embeddings=SimpleNamespace(create=AsyncMock(side_effect=create_embedding)),
    )


def test_list_embedding_models_probes_the_hub_and_reports_dimensions(client, monkeypatch):
    fake_client = _fake_embedding_client({"bge-m3": 1024, "e5": 768}, ["gpt-4o", "bge-m3", "e5"])
    monkeypatch.setattr(models_router, "_openai_client", fake_client)

    with patch("app.routers.models.redis_connector") as mock_redis:
        mock_redis.client.get.return_value = None

        response = client.get("/api/models/embeddings")

    assert response.status_code == 200
    assert response.json()["models"] == [{"id": "bge-m3", "dimension": 1024}, {"id": "e5", "dimension": 768}]
    cached_key, cached_value = mock_redis.client.set.call_args[0]
    assert cached_key == models_router._EMBEDDING_MODELS_CACHE_KEY
    assert json.loads(cached_value) == response.json()["models"]


def test_list_embedding_models_uses_cache_without_calling_the_hub(client, monkeypatch):
    fake_client = _fake_embedding_client({}, [])
    monkeypatch.setattr(models_router, "_openai_client", fake_client)

    with patch("app.routers.models.redis_connector") as mock_redis:
        mock_redis.client.get.return_value = json.dumps([{"id": "bge-m3", "dimension": 1024}])

        response = client.get("/api/models/embeddings")

    assert response.json()["models"] == [{"id": "bge-m3", "dimension": 1024}]
    fake_client.models.list.assert_not_called()


def test_list_embedding_models_returns_503_when_llm_hub_is_not_configured(client, monkeypatch):
    monkeypatch.setattr(models_router, "_openai_client", None)
    assert client.get("/api/models/embeddings").status_code == 503


def test_refresh_embedding_models_ignores_existing_cache(client, monkeypatch):
    fake_client = _fake_embedding_client({"bge-m3": 1024}, ["bge-m3"])
    monkeypatch.setattr(models_router, "_openai_client", fake_client)

    with patch("app.routers.models.redis_connector") as mock_redis:
        mock_redis.client.get.return_value = json.dumps([{"id": "stale", "dimension": 1}])

        response = client.post("/api/models/embeddings/refresh")

    assert response.json()["models"] == [{"id": "bge-m3", "dimension": 1024}]
    fake_client.models.list.assert_called_once()
