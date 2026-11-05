"""Les routes d'administration des modèles LLM : capacités définies par l'administrateur, modèles, ordre, mode auto,
hub. Le service est remplacé par une version en mémoire : rien n'est écrit dans la base de test partagée (des modèles
enregistrés y changeraient la réponse de `GET /api/models` aux autres tests), et les tests restent rapides."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.routers import admin_llm_models
from app.services import llm_hub, llm_models
from tests.access_support import As, _person  # noqa: F401


class FakeService:
    """Ce que les routes attendent de `app.services.llm_models`, gardé en mémoire."""

    DuplicateError = llm_models.DuplicateError
    NotFoundError = llm_models.NotFoundError

    def __init__(self) -> None:
        self.capabilities: list[SimpleNamespace] = []
        self.models: list[SimpleNamespace] = []
        self.auto = False
        self.detected: dict[str, list[str]] = {}

    # --- Capacités ---

    async def list_capabilities(self, db):
        return sorted(self.capabilities, key=lambda c: c.name)

    async def create_capability(self, db, *, name, description):
        if any(c.name == name for c in self.capabilities):
            raise self.DuplicateError
        capability = SimpleNamespace(id=uuid.uuid4(), name=name, description=description)
        self.capabilities.append(capability)
        return capability

    async def update_capability(self, db, capability_id, changes):
        capability = next((c for c in self.capabilities if c.id == capability_id), None)
        if capability is None:
            raise self.NotFoundError
        vars(capability).update(changes)
        return capability

    async def delete_capability(self, db, capability_id):
        capability = next((c for c in self.capabilities if c.id == capability_id), None)
        if capability is None:
            raise self.NotFoundError
        self.capabilities.remove(capability)
        for model in self.models:
            model.capabilities = [c for c in model.capabilities if c.id != capability_id]

    # --- Modèles ---

    async def list_models(self, db):
        return sorted(self.models, key=lambda m: m.position)

    async def create_model(self, db, *, name, capability_ids, enabled=True, types=None):
        if any(m.name == name for m in self.models):
            raise self.DuplicateError
        found = [c for c in self.capabilities if c.id in capability_ids]
        if len(found) != len(set(capability_ids)):
            raise self.NotFoundError
        model = SimpleNamespace(
            id=uuid.uuid4(), name=name, enabled=enabled, types=types, capabilities=found, position=len(self.models)
        )
        self.models.append(model)
        return model

    async def update_model(self, db, model_id, *, capability_ids=None, enabled=None):
        model = next((m for m in self.models if m.id == model_id), None)
        if model is None:
            raise self.NotFoundError
        if capability_ids is not None:
            model.capabilities = [c for c in self.capabilities if c.id in capability_ids]
        if enabled is not None:
            model.enabled = enabled
        return model

    async def reorder_models(self, db, model_ids):
        if sorted(model_ids) != sorted(m.id for m in self.models):
            raise self.NotFoundError
        for position, model_id in enumerate(model_ids):
            next(m for m in self.models if m.id == model_id).position = position
        return await self.list_models(db)

    async def delete_model(self, db, model_id):
        model = next((m for m in self.models if m.id == model_id), None)
        if model is None:
            raise self.NotFoundError
        self.models.remove(model)

    async def set_detected_types(self, db, by_name):
        self.detected.update(by_name)
        for model in self.models:
            if model.name in by_name:
                model.types = by_name[model.name]

    # --- Mode ---

    async def auto_mode(self, db):
        return self.auto

    async def set_auto_mode(self, db, value):
        self.auto = value
        return value


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> FakeService:
    fake = FakeService()
    monkeypatch.setattr(admin_llm_models, "llm_models", fake)
    monkeypatch.setattr(llm_hub, "cached_types", lambda name: None)  # pas de Redis
    return fake


@pytest.fixture
def admin(client: TestClient, service: FakeService):
    with As(_person("admin", [], admin=True)) as person:
        yield person


def test_a_capability_has_a_name_and_a_description_and_names_are_unique(client: TestClient, admin) -> None:
    created = client.post("/api/admin/llm-capabilities", json={"name": "Tâches lourdes", "description": "Raisonne."})
    again = client.post("/api/admin/llm-capabilities", json={"name": "Tâches lourdes", "description": "Autre."})
    blank = client.post("/api/admin/llm-capabilities", json={"name": "  ", "description": "x"})

    assert created.status_code == 201 and created.json()["description"] == "Raisonne."
    assert again.status_code == 409
    assert blank.status_code == 422


def test_a_capability_can_be_renamed_and_deleted(client: TestClient, admin) -> None:
    capability = client.post("/api/admin/llm-capabilities", json={"name": "Outils", "description": "x"}).json()

    renamed = client.patch(f"/api/admin/llm-capabilities/{capability['id']}", json={"name": "Outils externes"})
    deleted = client.delete(f"/api/admin/llm-capabilities/{capability['id']}")
    missing = client.delete(f"/api/admin/llm-capabilities/{capability['id']}")

    assert renamed.json()["name"] == "Outils externes" and renamed.json()["description"] == "x"
    assert deleted.status_code == 204 and missing.status_code == 404


def test_a_model_gets_the_capabilities_the_administrator_gives_it(client: TestClient, admin) -> None:
    capability = client.post("/api/admin/llm-capabilities", json={"name": "Outils", "description": "Appelle."}).json()

    model = client.post("/api/admin/llm-models", json={"name": "m1", "capability_ids": [capability["id"]]}).json()
    unknown = client.post("/api/admin/llm-models", json={"name": "m2", "capability_ids": [str(uuid.uuid4())]})
    duplicate = client.post("/api/admin/llm-models", json={"name": "m1"})

    assert model["capability_ids"] == [capability["id"]] and model["enabled"] is True and model["types"] is None
    assert unknown.status_code == 422 and duplicate.status_code == 409
    # Supprimer la capacité la retire des modèles.
    client.delete(f"/api/admin/llm-capabilities/{capability['id']}")
    assert client.get("/api/admin/llm-models").json()[0]["capability_ids"] == []


def test_a_model_can_be_disabled_and_removed(client: TestClient, admin) -> None:
    model = client.post("/api/admin/llm-models", json={"name": "m1"}).json()

    off = client.patch(f"/api/admin/llm-models/{model['id']}", json={"enabled": False}).json()
    gone = client.delete(f"/api/admin/llm-models/{model['id']}")

    assert off["enabled"] is False and gone.status_code == 204
    assert client.patch(f"/api/admin/llm-models/{model['id']}", json={"enabled": True}).status_code == 404


def test_models_are_ordered_and_a_new_one_comes_last(client: TestClient, admin) -> None:
    first = client.post("/api/admin/llm-models", json={"name": "a"}).json()
    second = client.post("/api/admin/llm-models", json={"name": "b"}).json()
    assert second["position"] > first["position"]

    reordered = client.put("/api/admin/llm-models/order", json={"model_ids": [second["id"], first["id"]]}).json()
    incomplete = client.put("/api/admin/llm-models/order", json={"model_ids": [first["id"]]})

    assert [m["id"] for m in reordered] == [second["id"], first["id"]]
    assert incomplete.status_code == 422


def test_the_mode_is_one_model_by_default_and_can_be_switched(client: TestClient, admin) -> None:
    assert client.get("/api/admin/llm-routing").json() == {"auto_mode": False}

    assert client.put("/api/admin/llm-routing", json={"auto_mode": True}).json() == {"auto_mode": True}
    assert client.get("/api/admin/llm-routing").json() == {"auto_mode": True}


def test_the_hub_gives_models_with_their_types_and_hides_registered_ones(
    client: TestClient, admin, service: FakeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/api/admin/llm-models", json={"name": "deja"})
    read: list[bool] = []

    async def fake_read(*, refresh: bool = False):
        read.append(refresh)
        found = [llm_hub.HubModel("deja", ["completion"]), llm_hub.HubModel("nouveau", ["completion", "audio"])]
        return found, datetime.now(UTC)

    monkeypatch.setattr(llm_hub, "read", fake_read)

    body = client.get("/api/admin/llm-hub-models", params={"refresh": True}).json()
    cached = client.get("/api/admin/llm-hub-models").json()

    assert body["models"] == [{"name": "nouveau", "types": ["completion", "audio"]}] and body["read_at"]
    assert read == [True, False]
    # Une relecture donne aux modèles enregistrés les types lus : on ne les saisit pas.
    assert service.detected == {"deja": ["completion"], "nouveau": ["completion", "audio"]}
    assert cached["models"] == body["models"]


def test_only_administrators_can_manage_models(client: TestClient, service: FakeService) -> None:
    with As(_person("simple", [])):
        assert client.get("/api/admin/llm-models").status_code == 403
        assert client.post("/api/admin/llm-capabilities", json={"name": "x", "description": "y"}).status_code == 403
        assert client.put("/api/admin/llm-routing", json={"auto_mode": True}).status_code == 403
