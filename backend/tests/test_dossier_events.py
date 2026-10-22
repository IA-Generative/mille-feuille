"""Journal d'événements du dossier (issue #169)."""

import uuid

import pytest
from fastapi.testclient import TestClient

ME = "dev-user"  # identité fixe du mode de test (VERIFY_TOKEN_MODEL=full-access)
INTERNAL_HEADERS = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


@pytest.fixture(autouse=True)
def _no_celery_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("dispatch_classification", "dispatch_entity_extraction", "dispatch_agent_execution"):
        monkeypatch.setattr(f"app.routers.dossiers.{name}", lambda dossier_id, *args, **kwargs: None)


def _create_analyse(client: TestClient, name: str = "Journal du dossier") -> dict:
    return client.post("/api/analyses", json={"name": name, "description": "Test"}).json()


def _create_dossier(client: TestClient, analyse_id: str | None = None, name: str = "Dossier journal") -> dict:
    payload = {"name": name}
    if analyse_id:
        payload["analyse_id"] = analyse_id
    return client.post("/api/dossiers", json=payload).json()


def _events(client: TestClient, dossier_id: str, **params) -> list[dict]:
    """Tous les événements du dossier, du plus récent au plus ancien."""
    response = client.get(f"/api/dossiers/{dossier_id}/events", params={"page_size": 100, **params})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _types(client: TestClient, dossier_id: str, **params) -> list[str]:
    return [e["type"] for e in _events(client, dossier_id, **params)]


def _set_status(client: TestClient, dossier_id: str, status_id: str):
    return client.put(f"/api/dossiers/{dossier_id}/workflow-status", json={"status_id": status_id})


# --- Création et lecture ---


def test_creation_is_recorded_with_its_author(client: TestClient) -> None:
    analyse = _create_analyse(client)
    dossier = _create_dossier(client, analyse["id"])

    (event,) = _events(client, dossier["id"])

    assert event["type"] == "created"
    assert event["actor_id"] == ME
    assert event["actor_name"] == "dev@example.com"
    assert event["payload"] == {"analyse_id": analyse["id"], "visibility": "restricted", "groups": ["/dev-tests"]}
    assert event["created_at"]


def test_dossier_without_analyse_records_creation_without_analyse(client: TestClient) -> None:
    dossier = _create_dossier(client, None, "Dossier à ranger")
    (event,) = _events(client, dossier["id"])
    assert event["payload"] == {"analyse_id": None, "visibility": "restricted", "groups": ["/dev-tests"]}


def test_events_are_listed_most_recent_first_and_paginated(client: TestClient) -> None:
    analyse = _create_analyse(client)
    initial, middle, final = analyse["statuses"]
    dossier = _create_dossier(client, analyse["id"])
    _set_status(client, dossier["id"], middle["id"])
    _set_status(client, dossier["id"], final["id"])

    types = _types(client, dossier["id"])
    first_page = client.get(f"/api/dossiers/{dossier['id']}/events", params={"page_size": 2}).json()

    assert types[0] == "closed" and types[-1] == "created"
    assert first_page["total"] == len(types) and first_page["pages"] == 2
    assert [e["type"] for e in first_page["items"]] == types[:2]


def test_events_of_unknown_dossier_is_404(client: TestClient) -> None:
    assert client.get(f"/api/dossiers/{uuid.uuid4()}/events").status_code == 404


# --- Consultations ---


def test_consultation_is_recorded_once_per_user_in_the_window(client: TestClient) -> None:
    dossier = _create_dossier(client)

    for _ in range(3):
        assert client.get(f"/api/dossiers/{dossier['id']}").status_code == 200

    consultations = _events(client, dossier["id"], type="consulted")
    assert len(consultations) == 1
    assert consultations[0]["actor_id"] == ME


def test_consultation_is_recorded_again_once_the_window_has_passed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    dossier = _create_dossier(client)
    client.get(f"/api/dossiers/{dossier['id']}")
    monkeypatch.setenv("CONSULTATION_DEDUP_MINUTES", "0")  # fenêtre vide : la précédente est hors fenêtre

    client.get(f"/api/dossiers/{dossier['id']}")

    assert len(_events(client, dossier["id"], type="consulted")) == 2


def test_listing_events_does_not_count_as_a_consultation(client: TestClient) -> None:
    dossier = _create_dossier(client)
    _events(client, dossier["id"])
    _events(client, dossier["id"])
    assert _types(client, dossier["id"]) == ["created"]


# --- Statuts ---


def test_status_change_records_from_and_to(client: TestClient) -> None:
    analyse = _create_analyse(client)
    initial, middle, _final = analyse["statuses"]
    dossier = _create_dossier(client, analyse["id"])

    _set_status(client, dossier["id"], middle["id"])

    event = _events(client, dossier["id"], type="status_changed")[0]
    assert event["actor_id"] == ME
    assert event["payload"] == {
        "from": {"id": initial["id"], "name": initial["name"]},
        "to": {"id": middle["id"], "name": middle["name"]},
    }


def test_closing_and_reopening_are_recorded(client: TestClient) -> None:
    analyse = _create_analyse(client)
    initial, _middle, final = analyse["statuses"]
    dossier = _create_dossier(client, analyse["id"])

    _set_status(client, dossier["id"], final["id"])
    _set_status(client, dossier["id"], initial["id"])

    types = _types(client, dossier["id"])
    assert types.count("closed") == 1 and types.count("reopened") == 1
    assert types.index("reopened") < types.index("closed")  # le plus récent d'abord
    closed = _events(client, dossier["id"], type="closed")[0]
    assert closed["payload"]["status"] == {"id": final["id"], "name": final["name"]}


def test_setting_the_same_status_records_nothing(client: TestClient) -> None:
    analyse = _create_analyse(client)
    dossier = _create_dossier(client, analyse["id"])
    before = _types(client, dossier["id"])

    _set_status(client, dossier["id"], analyse["statuses"][0]["id"])

    assert _types(client, dossier["id"]) == before


def test_refused_status_change_records_nothing(client: TestClient) -> None:
    analyse = _create_analyse(client)
    other = _create_analyse(client, "Autre analyse du journal")
    dossier = _create_dossier(client, analyse["id"])

    assert _set_status(client, dossier["id"], other["statuses"][0]["id"]).status_code == 400

    assert _types(client, dossier["id"]) == ["created"]


def test_replacing_a_used_status_records_the_move_for_each_dossier(client: TestClient) -> None:
    analyse = _create_analyse(client)
    initial, middle, final = analyse["statuses"]
    first = _create_dossier(client, analyse["id"], "Premier")
    second = _create_dossier(client, analyse["id"], "Second")
    for dossier in (first, second):
        _set_status(client, dossier["id"], middle["id"])

    client.put(
        f"/api/analyses/{analyse['id']}/statuses",
        json={
            "statuses": [
                {"id": s["id"], "name": s["name"], "is_initial": s["is_initial"], "is_final": s["is_final"]}
                for s in (initial, final)
            ],
            "replacements": {middle["id"]: final["id"]},
        },
    )

    for dossier in (first, second):
        moved = _events(client, dossier["id"], type="status_changed")[0]
        assert moved["payload"]["reason"] == "status_removed"
        assert moved["payload"]["from"]["id"] == middle["id"] and moved["payload"]["to"]["id"] == final["id"]
        assert "closed" in _types(client, dossier["id"])  # le statut de remplacement est final


def test_marking_a_status_final_records_the_closing(client: TestClient) -> None:
    analyse = _create_analyse(client)
    initial, middle, final = analyse["statuses"]
    dossier = _create_dossier(client, analyse["id"])
    _set_status(client, dossier["id"], middle["id"])

    client.put(
        f"/api/analyses/{analyse['id']}/statuses",
        json={
            "statuses": [
                {"id": initial["id"], "name": initial["name"], "is_initial": True},
                {"id": middle["id"], "name": middle["name"], "is_final": True},
                {"id": final["id"], "name": final["name"], "is_final": True},
            ]
        },
    )

    closed = _events(client, dossier["id"], type="closed")[0]
    assert closed["payload"]["reason"] == "status_flag_changed"


# --- Analyse, documents ---


def test_assigning_an_analyse_is_recorded(client: TestClient) -> None:
    analyse = _create_analyse(client)
    dossier = _create_dossier(client, None, "À ranger")

    client.post(f"/api/dossiers/{dossier['id']}/assign", json={"analyse_id": analyse["id"]})

    event = _events(client, dossier["id"], type="analyse_assigned")[0]
    assert event["payload"] == {"analyse_id": analyse["id"], "analyse_name": analyse["name"]}


def test_launch_and_stop_are_recorded(client: TestClient) -> None:
    analyse = _create_analyse(client)
    dossier = _create_dossier(client, analyse["id"])

    client.post(f"/api/dossiers/{dossier['id']}/launch")
    client.post(f"/api/dossiers/{dossier['id']}/launch")  # déjà en cours : rien de plus
    client.post(f"/api/dossiers/{dossier['id']}/stop")

    types = _types(client, dossier["id"])
    assert types.count("analysis_started") == 1 and types.count("analysis_stopped") == 1
    started = _events(client, dossier["id"], type="analysis_started")[0]
    assert started["actor_id"] == ME and started["payload"] == {"analyse_version": "v1"}


def _finish_all_steps(client: TestClient, dossier: dict, status: str) -> None:
    for step in dossier["execution_steps"]:
        client.post(
            f"/api/internal/execution-steps/{step['id']}/complete",
            json={"status": status, "output": "ok"},
            headers=INTERNAL_HEADERS,
        )


def test_end_of_analysis_is_recorded_as_a_system_event(client: TestClient) -> None:
    analyse = _create_analyse(client)
    dossier = _create_dossier(client, analyse["id"])
    launched = client.post(f"/api/dossiers/{dossier['id']}/launch").json()

    _finish_all_steps(client, launched, "terminé")

    (event,) = _events(client, dossier["id"], type="analysis_finished")
    assert event["actor_id"] is None and event["actor_name"] is None  # fait par le worker, pas par une personne
    assert _types(client, dossier["id"])[0] == "analysis_finished"


def test_failed_analysis_is_recorded(client: TestClient) -> None:
    analyse = _create_analyse(client)
    dossier = _create_dossier(client, analyse["id"])
    launched = client.post(f"/api/dossiers/{dossier['id']}/launch").json()

    _finish_all_steps(client, launched, "échec")

    assert _types(client, dossier["id"], type="analysis_failed") == ["analysis_failed"]
    assert _types(client, dossier["id"], type="analysis_finished") == []


def test_added_document_is_recorded_without_its_file_name(client: TestClient) -> None:
    dossier = _create_dossier(client)

    response = client.post(
        f"/api/dossiers/{dossier['id']}/documents",
        files=[("files", ("dupont-jean-cni.pdf", b"%PDF-1.4 contenu", "application/pdf"))],
    )
    assert response.status_code == 200, response.text

    event = _events(client, dossier["id"], type="document_added")[0]
    document_id = response.json()["documents"][0]["id"]
    assert event["payload"] == {"document_id": document_id, "mimetype": "application/pdf", "size": 16}
    assert "dupont" not in str(event)  # donnée d'usager : jamais dans le journal


# --- Filtres ---


def test_events_can_be_filtered_by_type_and_author(client: TestClient) -> None:
    analyse = _create_analyse(client)
    dossier = _create_dossier(client, analyse["id"])
    _set_status(client, dossier["id"], analyse["statuses"][1]["id"])
    client.get(f"/api/dossiers/{dossier['id']}")

    only_status = _types(client, dossier["id"], type="status_changed")
    several = _types(client, dossier["id"], type=["status_changed", "consulted"])
    by_me = _types(client, dossier["id"], actor_id=ME)
    by_someone_else = _types(client, dossier["id"], actor_id="quelqu-un-d-autre")

    assert only_status == ["status_changed"]
    assert sorted(several) == ["consulted", "status_changed"]
    assert len(by_me) == len(_types(client, dossier["id"]))
    assert by_someone_else == []


def test_unknown_event_type_filter_is_rejected(client: TestClient) -> None:
    dossier = _create_dossier(client)
    assert client.get(f"/api/dossiers/{dossier['id']}/events", params={"type": "inexistant"}).status_code == 422


# --- Append-only ---


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_the_journal_cannot_be_modified_through_the_api(client: TestClient, method: str) -> None:
    dossier = _create_dossier(client)
    event_id = _events(client, dossier["id"])[0]["id"]

    for path in (f"/api/dossiers/{dossier['id']}/events", f"/api/dossiers/{dossier['id']}/events/{event_id}"):
        response = client.request(method.upper(), path, json={"type": "created"})
        assert response.status_code in (404, 405)

    assert len(_events(client, dossier["id"])) == 1


# --- Cascade ---


def test_events_leave_with_their_dossier(client: TestClient) -> None:
    from document_helpers import run
    from sqlalchemy import func, select

    from app.models.dossier import Dossier
    from app.models.dossier_event import DossierEvent

    dossier = _create_dossier(client)
    dossier_id = uuid.UUID(dossier["id"])
    assert len(_events(client, dossier["id"])) == 1

    async def delete_dossier(db) -> None:
        await db.delete(await db.get(Dossier, dossier_id))
        await db.commit()

    async def count_events(db) -> int:
        return await db.scalar(
            select(func.count()).select_from(DossierEvent).where(DossierEvent.dossier_id == dossier_id)
        )

    run(client, delete_dossier)

    assert run(client, count_events) == 0  # le journal suit le dossier (cascade, cf. #94)


def test_dossier_created_by_the_internal_agent_is_journaled_under_the_person_it_acts_for(client: TestClient) -> None:
    analyse = _create_analyse(client)
    client.get("/api/auth/me")  # la personne est connue de l'annuaire, avec ses groupes

    created = client.post(
        "/api/internal/agent/dossiers",
        json={"name": "Dossier de l'agent", "analyse_id": analyse["id"]},
        headers={**INTERNAL_HEADERS, "X-Acting-User": ME},
    )

    assert created.status_code == 201, created.text
    (event,) = _events(client, created.json()["id"])
    # L'agent agit au nom de la personne (issue #222) : c'est elle qui est responsable de l'action.
    assert event["type"] == "created" and event["actor_id"] == ME


# --- Auteurs (filtre de l'historique) ---


def test_event_actors_lists_distinct_authors_without_the_system(client: TestClient) -> None:
    analyse = _create_analyse(client)
    dossier = _create_dossier(client, analyse["id"])
    client.get(f"/api/dossiers/{dossier['id']}")
    launched = client.post(f"/api/dossiers/{dossier['id']}/launch").json()
    _finish_all_steps(client, launched, "terminé")  # événement du système : sans auteur

    response = client.get(f"/api/dossiers/{dossier['id']}/events/actors")

    assert response.status_code == 200
    assert response.json() == [{"actor_id": ME, "actor_name": "dev@example.com"}]


def test_event_actors_of_unknown_dossier_is_404(client: TestClient) -> None:
    assert client.get(f"/api/dossiers/{uuid.uuid4()}/events/actors").status_code == 404


def test_launching_passes_the_person_to_the_agents(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Les agents appellent les serveurs MCP au nom de la personne qui a lancé l'analyse."""
    dispatched: list[tuple] = []
    monkeypatch.setattr("app.routers.dossiers.dispatch_agent_execution", lambda *args: dispatched.append(args))
    analyse = _create_analyse(client)
    dossier = _create_dossier(client, analyse["id"])

    client.post(f"/api/dossiers/{dossier['id']}/launch")

    assert dispatched == [(dossier["id"], ME)]
