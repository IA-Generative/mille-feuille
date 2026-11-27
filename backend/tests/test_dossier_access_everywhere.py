"""Accès aux dossiers par groupe (issue #177, partie 2) : la règle s'applique à **toutes** les routes d'un dossier,
au suivi, au tableau de bord, aux notifications, aux créneaux et aux conversations ; accès administrateur tracé
(#182)."""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.security.factory import RequestContext
from app.main import app
from app.services.due_date import today_in_paris
from tests.access_support import As
from tests.test_dossier_access import _create, _events

# --- Aucune route ne reste sans garde ---


def _dossier_operations() -> list[tuple[str, str]]:
    """Toutes les opérations `(méthode, chemin)` sous `/dossiers/{dossier_id}`, d'après le schéma OpenAPI : une route
    ajoutée plus tard y figure et est donc testée sans qu'on ait à y penser."""
    operations = []
    for path, item in app.openapi()["paths"].items():
        # Les routes internes (`/api/internal/…`) sont celles des workers, authentifiées par un jeton d'application et
        # hors périmètre utilisateur (issue #177) ; elles ne passent pas par cette règle.
        if "{dossier_id}" not in path or path.startswith("/api/internal/"):
            continue
        operations += [(method.upper(), path) for method in item if method in {"get", "post", "put", "patch", "delete"}]
    return sorted(operations)


def test_the_parcours_finds_the_dossier_routes() -> None:
    assert (
        len(_dossier_operations()) > 80
    )  # garde-fou : si le parcours ne trouve plus rien, le test suivant ne prouve rien


def _concrete_path(template: str, dossier_id: str) -> str:
    segments = template.replace("{dossier_id}", dossier_id).split("/")
    return "/".join(str(uuid.uuid4()) if segment.startswith("{") else segment for segment in segments)


@pytest.mark.parametrize(("method", "template"), _dossier_operations(), ids=lambda v: v)
def test_a_person_outside_the_groups_gets_404_on_every_dossier_route(
    client: TestClient,
    analyse: dict,
    world: dict,
    method: str,
    template: str,
) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)  # restreint à /a
    path = _concrete_path(template, dossier["id"])

    with As(world["bob"]):
        response = client.request(method, path, json={} if method != "GET" else None)

    # 404 « Dossier introuvable », jamais 403 ni 422 ni 200 : ni la validation du corps ni la route ne s'exécutent.
    assert response.status_code == 404, f"{method} {path} -> {response.status_code} {response.text[:200]}"
    assert response.json()["detail"] == "Dossier introuvable"


# --- Accès administrateur tracé (#182) ---


def _admin_events(client: TestClient, dossier_id: str) -> list[dict]:
    return _events(client, dossier_id, "admin_access")


def test_an_administrator_outside_the_groups_is_traced(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["bob"]):
        dossier = _create(client, analyse)  # /b : root n'est pas dans ce groupe
    with As(world["root"]):
        client.get(f"/api/dossiers/{dossier['id']}")
        client.get(f"/api/dossiers/{dossier['id']}/notes")  # une seconde lecture dans la fenêtre : pas de doublon
        client.post(f"/api/dossiers/{dossier['id']}/notes", json={"content": "note d'administrateur"})
        events = _admin_events(client, dossier["id"])

    payloads = sorted((e["payload"]["method"], e["payload"]["write"]) for e in events)
    assert payloads == [("GET", False), ("POST", True)]
    assert all(e["actor_id"] == world["root"].user_id for e in events)


def test_every_write_by_an_administrator_is_traced_but_reads_are_deduplicated(
    client: TestClient, analyse: dict, world: dict
) -> None:
    with As(world["bob"]):
        dossier = _create(client, analyse)
    with As(world["root"]):
        for index in range(3):
            client.post(f"/api/dossiers/{dossier['id']}/notes", json={"content": f"note {index}"})
        events = _admin_events(client, dossier["id"])

    assert len([e for e in events if e["payload"]["write"]]) == 3


def test_an_administrator_who_is_a_member_is_not_traced(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)  # /a : root en fait partie
    with As(world["root"]):
        client.get(f"/api/dossiers/{dossier['id']}")
        assert _admin_events(client, dossier["id"]) == []


def test_an_administrator_on_an_open_dossier_is_not_traced(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["bob"]):
        dossier = _create(client, analyse, visibility="analyse")
    with As(world["root"]):
        client.get(f"/api/dossiers/{dossier['id']}")
        assert _admin_events(client, dossier["id"]) == []


def test_admin_accesses_are_only_shown_to_administrators(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["bob"]):
        dossier = _create(client, analyse)
    with As(world["root"]):
        client.get(f"/api/dossiers/{dossier['id']}")
        root_sees = _admin_events(client, dossier["id"])
        all_for_root = client.get(f"/api/dossiers/{dossier['id']}/events", params={"page_size": 100}).json()["items"]
    with As(world["bob"]):
        bob_sees = _admin_events(client, dossier["id"])
        all_for_bob = client.get(f"/api/dossiers/{dossier['id']}/events", params={"page_size": 100}).json()["items"]
        actors = client.get(f"/api/dossiers/{dossier['id']}/events/actors").json()

    assert len(root_sees) == 1 and any(e["type"] == "admin_access" for e in all_for_root)
    assert bob_sees == [] and not any(e["type"] == "admin_access" for e in all_for_bob)
    assert world["root"].user_id not in [a["actor_id"] for a in actors]


def test_the_presence_heartbeat_is_not_counted_as_a_modification(
    client: TestClient, analyse: dict, world: dict
) -> None:
    with As(world["bob"]):
        dossier = _create(client, analyse)
    with As(world["root"]):
        client.get(f"/api/dossiers/{dossier['id']}")
        for _ in range(3):
            client.put(f"/api/dossiers/{dossier['id']}/analyse-dossier/presence", json={})
        events = _admin_events(client, dossier["id"])

    assert [e["payload"]["write"] for e in events] == [False]


# --- Suivi ---


def _tracked_ids(client: TestClient, **params) -> tuple[set[str], int]:
    ids: set[str] = set()
    page, total = 1, 0
    while True:
        body = client.get("/api/tracking", params={"page": page, "page_size": 100, **params}).json()
        ids |= {row["id"] for row in body["items"]}
        total = body["total"]
        if page >= body["pages"]:
            return ids, total
        page += 1


def test_tracking_lists_and_counts_only_visible_dossiers(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
    with As(world["bob"]):
        ids, total = _tracked_ids(client, analyse_id=analyse["id"])
        found = client.get("/api/tracking", params={"search": dossier["name"], "analyse_id": analyse["id"]}).json()
    with As(world["carol"]):
        carol_ids, carol_total = _tracked_ids(client, analyse_id=analyse["id"])

    assert dossier["id"] not in ids and total == 0 and found["total"] == 0
    assert dossier["id"] in carol_ids and carol_total == 1


# --- Tableau de bord, notifications, créneaux, conversations ---


def _left(person: RequestContext, groups: list[str]) -> RequestContext:
    """La même personne, après un changement de groupes dans Keycloak."""
    return RequestContext(**{**person.__dict__, "groups": groups})


def _assign(client: TestClient, dossier_id: str, person: RequestContext) -> None:
    response = client.put(f"/api/dossiers/{dossier_id}/assignee", json={"assignee_id": person.user_id})
    assert response.status_code == 200, response.text


def test_the_dashboard_forgets_dossiers_i_can_no_longer_see(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
        _assign(client, dossier["id"], world["alice"])
        client.put(
            f"/api/dossiers/{dossier['id']}/due-at", json={"due_at": (today_in_paris() + timedelta(days=2)).isoformat()}
        )
        before = client.get("/api/dashboard").json()

    with As(_left(world["alice"], ["/ailleurs"])):
        after = client.get("/api/dashboard").json()

    assert before["stats"]["total_dossiers"] == 1 and len(before["urgencies"]) == 1
    assert after["stats"]["total_dossiers"] == 0
    assert after["urgencies"] == [] and after["status_counts"] == [] and after["activity"] == []


def test_notifications_are_masked_after_an_access_loss(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        client.get("/api/notifications")  # curseur posé
        dossier = _create(client, analyse)
    with As(world["carol"]):
        _assign(client, dossier["id"], world["alice"])
    with As(world["alice"]):
        (before,) = client.get("/api/notifications").json()

    with As(_left(world["alice"], ["/ailleurs"])):
        (after,) = client.get("/api/notifications").json()

    assert before["accessible"] is True and before["dossier_name"] == dossier["name"]
    assert after["accessible"] is False and after["dossier_id"] is None and after["dossier_name"] is None
    assert after["id"] == before["id"] and after["message"] == before["message"]  # elle reste dans la liste


def test_no_notification_is_created_for_a_dossier_i_cannot_see(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
        _assign(client, dossier["id"], world["alice"])
    away = _left(world["alice"], ["/ailleurs"])
    with As(away):
        client.get("/api/notifications")  # curseur posé : alice ne voit plus le dossier
    with As(world["carol"]):
        final = next(s for s in analyse["statuses"] if s["is_final"])
        client.put(f"/api/dossiers/{dossier['id']}/workflow-status", json={"status_id": final["id"]})

    with As(away):
        assert client.get("/api/notifications").json() == []


def test_slots_follow_the_access(client: TestClient, analyse: dict, world: dict) -> None:
    slot = {
        "start": "2030-01-02T09:00:00+01:00",
        "end": "2030-01-02T10:00:00+01:00",
        "reminders": [],
    }
    with As(world["alice"]):
        dossier = _create(client, analyse)
        assert client.put(f"/api/dossiers/{dossier['id']}/slot", json=slot).status_code == 200
        assert len(client.get("/api/slots").json()) == 1
    with As(world["bob"]):
        assert client.put(f"/api/dossiers/{dossier['id']}/slot", json=slot).status_code == 404

    with As(_left(world["alice"], ["/ailleurs"])):
        assert client.get("/api/slots").json() == []  # le créneau existe toujours, mais le dossier n'est plus visible


def test_my_conversations_list_hides_dossiers_i_cannot_see(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
        client.post(f"/api/dossiers/{dossier['id']}/conversations")
        before = client.get("/api/conversations").json()["total"]
    with As(_left(world["alice"], ["/ailleurs"])):
        after = client.get("/api/conversations").json()

    assert before == 1 and after["total"] == 0 and after["items"] == []


# --- Annuaire filtré par accès ---


def _is_proposed(client: TestClient, person: RequestContext, dossier_id: str) -> bool:
    """La personne est-elle proposée pour ce dossier ? (recherche sur son nom, unique : la base de test est grande)."""
    found = client.get("/api/users", params={"dossier_id": dossier_id, "q": person.last_name}).json()
    return person.user_id in [p["id"] for p in found]


def test_the_directory_can_be_limited_to_people_with_access(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)  # /a
        open_dossier = _create(client, analyse, visibility="analyse")
        proposed = {
            name: _is_proposed(client, world[name], dossier["id"]) for name in ("alice", "bob", "carol", "root")
        }
        bob_for_open = _is_proposed(client, world["bob"], open_dossier["id"])

    assert proposed == {"alice": True, "bob": False, "carol": True, "root": True}  # bob : /b seulement
    assert bob_for_open is False  # « selon l'analyse » : seulement qui a accès à l'analyse (#662)
    with As(world["bob"]):
        assert client.get("/api/users", params={"dossier_id": dossier["id"]}).status_code == 404
