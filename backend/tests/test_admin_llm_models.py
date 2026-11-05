"""Les modèles LLM de l'administration : capacités définies par l'administrateur, modèles, ordre, mode auto."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.services import llm_hub
from tests.access_support import As, _person  # noqa: F401


@pytest.fixture
def admin(client: TestClient):
    person = _person("admin", [], admin=True)
    with As(person):
        yield person


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def test_a_capability_has_a_name_and_a_description_and_names_are_unique(client: TestClient, admin) -> None:
    name = f"Tâches lourdes {_suffix()}"

    created = client.post("/api/admin/llm-capabilities", json={"name": name, "description": "Raisonne beaucoup."})
    again = client.post("/api/admin/llm-capabilities", json={"name": name, "description": "Autre."})

    assert created.status_code == 201 and created.json()["description"] == "Raisonne beaucoup."
    assert again.status_code == 409


def test_a_model_gets_the_capabilities_the_administrator_gives_it(client: TestClient, admin) -> None:
    capability = client.post(
        "/api/admin/llm-capabilities", json={"name": f"Outils {_suffix()}", "description": "Appelle des outils."}
    ).json()

    model = client.post(
        "/api/admin/llm-models", json={"name": f"modele-{_suffix()}", "capability_ids": [capability["id"]]}
    ).json()
    unknown = client.post(
        "/api/admin/llm-models", json={"name": f"modele-{_suffix()}", "capability_ids": [str(uuid.uuid4())]}
    )

    assert model["capability_ids"] == [capability["id"]] and model["enabled"] is True
    assert unknown.status_code == 422
    # Supprimer la capacité la retire des modèles.
    assert client.delete(f"/api/admin/llm-capabilities/{capability['id']}").status_code == 204
    listed = {m["id"]: m for m in client.get("/api/admin/llm-models").json()}
    assert listed[model["id"]]["capability_ids"] == []


def test_models_are_ordered_and_a_new_one_comes_last(client: TestClient, admin) -> None:
    first = client.post("/api/admin/llm-models", json={"name": f"a-{_suffix()}"}).json()
    second = client.post("/api/admin/llm-models", json={"name": f"b-{_suffix()}"}).json()
    assert second["position"] > first["position"]

    everyone = [m["id"] for m in client.get("/api/admin/llm-models").json()]
    swapped = [second["id"], *[i for i in everyone if i != second["id"]]]
    reordered = client.put("/api/admin/llm-models/order", json={"model_ids": swapped}).json()
    incomplete = client.put("/api/admin/llm-models/order", json={"model_ids": [first["id"]]})

    assert [m["id"] for m in reordered] == swapped
    assert incomplete.status_code == 422


def test_the_mode_is_one_model_by_default_and_can_be_switched(client: TestClient, admin) -> None:
    assert client.put("/api/admin/llm-routing", json={"auto_mode": False}).json() == {"auto_mode": False}

    assert client.put("/api/admin/llm-routing", json={"auto_mode": True}).json() == {"auto_mode": True}
    assert client.get("/api/admin/llm-routing").json() == {"auto_mode": True}
    client.put("/api/admin/llm-routing", json={"auto_mode": False})


def test_the_hub_only_gives_names_and_hides_registered_models(
    client: TestClient, admin, monkeypatch: pytest.MonkeyPatch
) -> None:
    registered = f"deja-{_suffix()}"
    client.post("/api/admin/llm-models", json={"name": registered})
    read: list[bool] = []

    async def fake_read(*, refresh: bool = False):
        from datetime import UTC, datetime

        read.append(refresh)
        return [registered, "nouveau-modele"], datetime.now(UTC)

    monkeypatch.setattr(llm_hub, "read", fake_read)

    body = client.get("/api/admin/llm-hub-models", params={"refresh": True}).json()

    assert body["models"] == ["nouveau-modele"] and body["read_at"] and read == [True]


def test_only_administrators_can_manage_models(client: TestClient) -> None:
    with As(_person("simple", [])):
        assert client.get("/api/admin/llm-models").status_code == 403
        assert client.post("/api/admin/llm-capabilities", json={"name": "x", "description": "y"}).status_code == 403
