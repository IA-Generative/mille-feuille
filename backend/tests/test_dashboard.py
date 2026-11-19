"""Tableau de bord personnel (issue #174) : indicateurs, urgences, statuts, non affectés, activité."""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.security.factory import RequestContext, get_current_user
from app.main import app
from app.services.due_date import today_in_paris


def _day(offset: int) -> str:
    return (today_in_paris() + timedelta(days=offset)).isoformat()


def _person(suffix: str, *, admin: bool = False) -> RequestContext:
    return RequestContext(
        user_id=f"tdb-{suffix}",
        email=f"{suffix}@example.org",
        roles=["admin"] if admin else [],
        is_admin=admin,
        first_name="Tableau",
        last_name=suffix,
        groups=["/dev-tests"],
    )


@pytest.fixture
def me(client: TestClient):
    """Une personne neuve, connue de l'annuaire : ses dossiers sont les seuls de son tableau de bord."""
    person = _person(uuid.uuid4().hex[:8])
    app.dependency_overrides[get_current_user] = lambda: person
    client.get("/api/auth/me")
    yield person
    del app.dependency_overrides[get_current_user]


@pytest.fixture
def analyse(client: TestClient) -> dict:
    created = client.post("/api/analyses", json={"name": f"Bord {uuid.uuid4().hex[:6]}", "description": "T"}).json()
    return client.get(f"/api/analyses/{created['id']}").json()


def _assigned_dossier(client: TestClient, analyse: dict, me: RequestContext, name: str, due: int | None = None) -> dict:
    dossier = client.post("/api/dossiers", json={"name": name, "analyse_id": analyse["id"]}).json()
    client.put(f"/api/dossiers/{dossier['id']}/assignee", json={"assignee_id": me.user_id})
    if due is not None:
        client.put(f"/api/dossiers/{dossier['id']}/due-at", json={"due_at": _day(due)})
    return dossier


def _close(client: TestClient, analyse: dict, dossier_id: str) -> None:
    final = next(s for s in analyse["statuses"] if s["is_final"])
    client.put(f"/api/dossiers/{dossier_id}/workflow-status", json={"status_id": final["id"]})


def _dashboard(client: TestClient) -> dict:
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    return response.json()


def test_empty_dashboard_for_a_new_person(client: TestClient, me) -> None:
    board = _dashboard(client)

    assert board["stats"] == {
        "total_dossiers": 0,
        "closed_dossiers": 0,
        "completed_this_week": 0,
        "completed_prev_week": 0,
        "weekly_closed": [0, 0, 0, 0],
        "avg_processing_days": 0.0,
        "on_time_rate": 0.0,
    }
    assert board["urgencies"] == [] and board["others"] == [] and board["status_counts"] == [] and board["activity"] == []


def test_only_my_dossiers_count(client: TestClient, analyse: dict, me) -> None:
    _assigned_dossier(client, analyse, me, "À moi")
    client.post("/api/dossiers", json={"name": "À personne", "analyse_id": analyse["id"]})

    assert _dashboard(client)["stats"]["total_dossiers"] == 1


def test_closing_updates_the_counters_and_the_week(client: TestClient, analyse: dict, me) -> None:
    open_one = _assigned_dossier(client, analyse, me, "Ouvert")
    closed = _assigned_dossier(client, analyse, me, "Clos")
    _close(client, analyse, closed["id"])

    stats = _dashboard(client)["stats"]

    assert stats["total_dossiers"] == 2 and stats["closed_dossiers"] == 1
    assert stats["completed_this_week"] == 1 and stats["completed_prev_week"] == 0
    assert stats["weekly_closed"] == [0, 0, 0, 1]
    assert stats["avg_processing_days"] >= 0
    assert open_one["id"]


def test_on_time_rate_counts_closed_dossiers_with_a_due_date(client: TestClient, analyse: dict, me) -> None:
    in_time = _assigned_dossier(client, analyse, me, "Dans les temps", due=3)
    late = _assigned_dossier(client, analyse, me, "En retard", due=-2)
    no_due = _assigned_dossier(client, analyse, me, "Sans échéance")
    for dossier in (in_time, late, no_due):
        _close(client, analyse, dossier["id"])

    assert _dashboard(client)["stats"]["on_time_rate"] == 0.5  # 1 sur 2 : celui sans échéance ne compte pas


def test_urgencies_follow_the_thresholds_and_skip_closed_dossiers(client: TestClient, analyse: dict, me) -> None:
    late = _assigned_dossier(client, analyse, me, "Dépassé", due=-3)
    soon = _assigned_dossier(client, analyse, me, "Bientôt", due=5)
    _assigned_dossier(client, analyse, me, "Loin", due=200)
    _assigned_dossier(client, analyse, me, "Sans échéance")
    closed = _assigned_dossier(client, analyse, me, "Clos en retard", due=-10)
    _close(client, analyse, closed["id"])

    urgencies = _dashboard(client)["urgencies"]

    assert [u["dossier_id"] for u in urgencies] == [late["id"], soon["id"]]  # par échéance
    assert [(u["level"], u["days_left"]) for u in urgencies] == [("overdue", -3), ("soon", 5)]
    assert urgencies[0]["analyse_name"] == analyse["name"] and urgencies[0]["color"]
    assert urgencies[0]["status_label"]


def test_others_hold_open_dossiers_that_are_not_urgent(client: TestClient, analyse: dict, me) -> None:
    _assigned_dossier(client, analyse, me, "Bientôt", due=5)
    far = _assigned_dossier(client, analyse, me, "Loin", due=200)
    no_due = _assigned_dossier(client, analyse, me, "Sans échéance")
    closed = _assigned_dossier(client, analyse, me, "Clos", due=200)
    _close(client, analyse, closed["id"])

    board = _dashboard(client)

    assert [o["dossier_id"] for o in board["others"]] == [far["id"], no_due["id"]]  # sans échéance en dernier
    assert board["others"][1]["due_at"] is None and board["others"][0]["slot"] is None
    assert len(board["urgencies"]) == 1


def test_thresholds_of_each_analyse_decide_who_is_urgent(client: TestClient, analyse: dict, me) -> None:
    dossier = _assigned_dossier(client, analyse, me, "Seuil serré", due=20)
    assert _dashboard(client)["urgencies"][0]["dossier_id"] == dossier["id"]  # 20 j ≤ 30 j : proche

    client.put(
        f"/api/analyses/{analyse['id']}/due-settings",
        json={
            "default_due_days": None,
            "thresholds": {
                "far_color": "#18753c",
                "steps": [{"days": 7, "color": "#ce0500"}],
                "overdue_color": "#8a0000",
            },
        },
    )

    assert _dashboard(client)["urgencies"] == []  # 20 j > 7 j : loin


def test_status_counts_group_open_dossiers_by_status(client: TestClient, analyse: dict, me) -> None:
    for name in ("A", "B"):
        _assigned_dossier(client, analyse, me, name)
    closed = _assigned_dossier(client, analyse, me, "C")
    _close(client, analyse, closed["id"])
    initial = next(s for s in analyse["statuses"] if s["is_initial"])

    counts = _dashboard(client)["status_counts"]

    assert counts == [
        {"status_id": initial["id"], "label": initial["name"], "analyse_name": analyse["name"], "count": 2}
    ]


def test_unassigned_is_reserved_to_administrators(client: TestClient, analyse: dict, me) -> None:
    client.post("/api/dossiers", json={"name": "Sans responsable", "analyse_id": analyse["id"]})

    assert _dashboard(client)["unassigned"] is None  # `me` n'est pas administrateur

    admin = _person(uuid.uuid4().hex[:8], admin=True)
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        listed = _dashboard(client)["unassigned"]
    finally:
        app.dependency_overrides[get_current_user] = lambda: me
    # La liste est bornée (les plus anciens d'abord) : la base de test en contient d'autres, on vérifie sa forme.
    assert 1 <= len(listed) <= 50
    assert set(listed[0]) == {"dossier_id", "dossier_name", "analyse_name", "created_at"}
    assert [u["created_at"] for u in listed] == sorted(u["created_at"] for u in listed)


def test_activity_shows_what_others_did_on_my_dossiers(client: TestClient, analyse: dict, me) -> None:
    dossier = _assigned_dossier(client, analyse, me, "Activité")
    other = _person(uuid.uuid4().hex[:8])
    final = next(s for s in analyse["statuses"] if s["is_final"])
    app.dependency_overrides[get_current_user] = lambda: other
    try:
        client.put(f"/api/dossiers/{dossier['id']}/workflow-status", json={"status_id": final["id"]})
    finally:
        app.dependency_overrides[get_current_user] = lambda: me

    activity = _dashboard(client)["activity"]

    assert len(activity) == 1
    assert activity[0]["kind"] == "status_changed" and activity[0]["dossier_id"] == dossier["id"]
    assert activity[0]["message"].endswith(f"par Tableau {other.last_name}")


def test_my_own_actions_are_not_activity(client: TestClient, analyse: dict, me) -> None:
    dossier = _assigned_dossier(client, analyse, me, "Mes actions")
    _close(client, analyse, dossier["id"])  # par moi

    assert _dashboard(client)["activity"] == []
