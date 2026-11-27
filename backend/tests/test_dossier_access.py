"""Accès aux dossiers par groupe (issue #177, partie 1) : visibilité, création, modification, affectation."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security.factory import RequestContext
from app.services.dossier_access import can_view
from tests.access_support import As, _person  # noqa: F401

# --- Règle pure ---


@pytest.mark.parametrize(
    ("is_admin", "groups", "visibility", "has_analyse", "dossier_groups", "expected"),
    [
        (True, [], "restricted", True, ["/a"], True),  # un administrateur voit tout
        (False, ["/a"], "restricted", True, ["/a"], True),  # membre d'un groupe associé
        (False, ["/b"], "restricted", True, ["/a"], False),  # membre d'un autre groupe
        (False, [], "restricted", True, ["/a"], False),  # aucun groupe
        (False, ["/a/sous"], "restricted", True, ["/a"], False),  # pas d'héritage vers le bas
        (False, ["/"], "restricted", True, ["/a"], False),  # ni vers le haut
        (False, [], "analyse", True, [], True),  # « selon l'analyse » : tout le monde
        (False, [], "analyse", False, [], False),  # « à ranger » : pas d'analyse dont hériter
        (False, ["/a"], "analyse", False, ["/a"], True),  # « à ranger » : suit les groupes associés
    ],
)
def test_can_view_rule(is_admin, groups, visibility, has_analyse, dossier_groups, expected) -> None:
    assert (
        can_view(
            is_admin=is_admin,
            groups=groups,
            visibility=visibility,
            has_analyse=has_analyse,
            dossier_groups=dossier_groups,
            has_analyse_access=True,
        )
        is expected
    )


def test_a_dossier_following_its_analyse_needs_access_to_it() -> None:
    seen = dict(is_admin=False, groups=["/a"], visibility="analyse", has_analyse=True, dossier_groups=["/a"])
    assert can_view(**seen, has_analyse_access=False) is False
    assert can_view(**seen, has_analyse_access=True) is True


def _create(client: TestClient, analyse: dict | None, **body) -> dict:
    payload = {"name": "Dossier d'accès", **body}
    if analyse:
        payload["analyse_id"] = analyse["id"]
    response = client.post("/api/dossiers", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _list_ids(client: TestClient) -> set[str]:
    ids: set[str] = set()
    page = 1
    while True:
        body = client.get("/api/dossiers", params={"page": page, "page_size": 100}).json()
        ids |= {d["id"] for d in body["items"]}
        if page >= body["pages"]:
            return ids
        page += 1


def _access(client: TestClient, dossier_id: str) -> dict:
    return client.get(f"/api/dossiers/{dossier_id}/access").json()


def _put_access(client: TestClient, dossier_id: str, visibility: str, groups: list[str]):
    return client.put(f"/api/dossiers/{dossier_id}/access", json={"visibility": visibility, "group_paths": groups})


def _events(client: TestClient, dossier_id: str, type: str) -> list[dict]:
    return client.get(f"/api/dossiers/{dossier_id}/events", params={"type": type}).json()["items"]


# --- Création ---


def test_a_new_dossier_is_restricted_to_all_my_groups_by_default(
    client: TestClient, analyse: dict, world: dict
) -> None:
    with As(world["carol"]):
        dossier = _create(client, analyse)
        access = _access(client, dossier["id"])

    assert access["visibility"] == "restricted"
    assert [g["path"] for g in access["groups"]] == sorted([world["a"], world["b"]])


def test_creation_can_pick_some_of_my_groups(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["carol"]):
        dossier = _create(client, analyse, group_paths=[world["b"]])

        assert [g["path"] for g in _access(client, dossier["id"])["groups"]] == [world["b"]]


def test_creation_refuses_a_group_that_is_not_mine(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        response = client.post(
            "/api/dossiers", json={"name": "X", "analyse_id": analyse["id"], "group_paths": [world["b"]]}
        )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "group_not_yours",
        "message": "On ne peut associer que ses propres groupes.",
        "groups": [world["b"]],
    }


def test_even_an_administrator_can_only_associate_their_own_groups(
    client: TestClient, analyse: dict, world: dict
) -> None:
    with As(world["root"]):
        response = client.post(
            "/api/dossiers", json={"name": "X", "analyse_id": analyse["id"], "group_paths": [world["b"]]}
        )

    assert response.status_code == 422


def test_a_restricted_dossier_needs_at_least_one_group(client: TestClient, analyse: dict, world: dict) -> None:
    nobody = _person("nobody", [])
    with As(nobody):
        no_group = client.post("/api/dossiers", json={"name": "X", "analyse_id": analyse["id"]})
    with As(world["alice"]):
        empty = client.post("/api/dossiers", json={"name": "X", "analyse_id": analyse["id"], "group_paths": []})

    assert no_group.status_code == 422 and no_group.json()["detail"]["code"] == "groups_required"
    assert empty.status_code == 422 and empty.json()["detail"]["code"] == "groups_required"


def test_a_dossier_open_to_the_analyse_needs_no_group(client: TestClient, analyse: dict, world: dict) -> None:
    nobody = _person("nobody", [])
    with As(nobody):
        dossier = _create(client, analyse, visibility="analyse", group_paths=["/ignoré"])
        access = _access(client, dossier["id"])

    assert access["visibility"] == "analyse" and access["groups"] == []


def test_creation_is_traced_with_its_access(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
        (event,) = _events(client, dossier["id"], "created")

    assert event["payload"]["visibility"] == "restricted" and event["payload"]["groups"] == [world["a"]]


# --- Qui voit quoi ---


def test_a_restricted_dossier_is_seen_only_by_its_groups_and_administrators(
    client: TestClient, analyse: dict, world: dict
) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
    seen = {}
    for name in ("alice", "bob", "carol", "root"):
        with As(world[name]):
            seen[name] = (
                dossier["id"] in _list_ids(client),
                client.get(f"/api/dossiers/{dossier['id']}").status_code,
            )

    assert seen == {"alice": (True, 200), "bob": (False, 404), "carol": (True, 200), "root": (True, 200)}


def test_an_invisible_dossier_answers_404_everywhere_not_403(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)

    with As(world["bob"]):
        assert client.get(f"/api/dossiers/{dossier['id']}").status_code == 404
        assert client.get(f"/api/dossiers/{dossier['id']}/access").status_code == 404
        assert _put_access(client, dossier["id"], "analyse", []).status_code == 404
        assert client.put(f"/api/dossiers/{dossier['id']}/assignee", json={"assignee_id": None}).status_code == 404


def test_an_existing_style_dossier_is_visible_to_everyone(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse, visibility="analyse")

    with As(world["bob"]):
        assert dossier["id"] in _list_ids(client)
        assert client.get(f"/api/dossiers/{dossier['id']}").status_code == 200


def test_a_dossier_to_sort_follows_its_groups(client: TestClient, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, None)
    with As(world["bob"]):
        assert client.get(f"/api/dossiers/{dossier['id']}").status_code == 404
    with As(world["carol"]):
        assert client.get(f"/api/dossiers/{dossier['id']}").status_code == 200


def test_the_creator_has_no_right_of_their_own(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
    left = RequestContext(**{**world["alice"].__dict__, "groups": ["/ailleurs"]})  # alice a quitté le groupe

    with As(left):
        assert dossier["id"] not in _list_ids(client)
        assert client.get(f"/api/dossiers/{dossier['id']}").status_code == 404


def test_a_group_is_matched_exactly_without_inheritance(client: TestClient, analyse: dict, world: dict) -> None:
    parent = world["a"]
    with As(world["alice"]):
        dossier = _create(client, analyse)
    child = _person("child", [f"{parent}/equipe"])
    with As(child):
        assert client.get(f"/api/dossiers/{dossier['id']}").status_code == 404


# --- Lire et modifier l'accès ---


def test_access_is_readable_by_those_who_see_the_dossier(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
        access = _access(client, dossier["id"])

    assert access["can_edit"] is False and access["available_groups"] == [world["a"]]
    assert access["groups"][0]["granted_by"] == world["alice"].user_id


def test_only_administrators_change_the_access(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
        response = _put_access(client, dossier["id"], "analyse", [])

    assert response.status_code == 403
    with As(world["root"]):
        assert _put_access(client, dossier["id"], "analyse", []).status_code == 200


def test_an_administrator_adds_one_of_their_groups_and_removes_any(
    client: TestClient, analyse: dict, world: dict
) -> None:
    with As(world["bob"]):
        dossier = _create(client, analyse)  # groupe /b, que root n'a pas
    with As(world["root"]):
        added = _put_access(client, dossier["id"], "restricted", [world["b"], world["a"]]).json()
        swapped = _put_access(
            client, dossier["id"], "restricted", [world["a"]]
        ).json()  # retire /b qui n'est pas à root

    assert [g["path"] for g in added["groups"]] == sorted([world["a"], world["b"]])
    assert [g["path"] for g in swapped["groups"]] == [world["a"]]


def test_an_administrator_cannot_add_a_group_that_is_not_theirs(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
    with As(world["root"]):
        response = _put_access(client, dossier["id"], "restricted", [world["a"], world["b"]])

    assert response.status_code == 422 and response.json()["detail"]["groups"] == [world["b"]]


def test_a_restricted_dossier_keeps_at_least_one_group(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
    with As(world["root"]):
        response = _put_access(client, dossier["id"], "restricted", [])

    assert response.status_code == 422 and response.json()["detail"]["code"] == "groups_required"


def test_switching_visibility_opens_and_closes_the_dossier(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
    with As(world["root"]):
        _put_access(client, dossier["id"], "analyse", [world["a"]])
    with As(world["bob"]):
        assert client.get(f"/api/dossiers/{dossier['id']}").status_code == 200
    with As(world["root"]):
        _put_access(client, dossier["id"], "restricted", [world["a"]])  # retour en arrière
    with As(world["bob"]):
        assert client.get(f"/api/dossiers/{dossier['id']}").status_code == 404


def test_every_access_change_is_traced(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
    with As(world["root"]):
        _put_access(client, dossier["id"], "analyse", [])
        _put_access(client, dossier["id"], "analyse", [])  # sans changement : rien de plus
        events = _events(client, dossier["id"], "access_changed")

    assert len(events) == 1
    assert events[0]["payload"] == {
        "visibility": {"from": "restricted", "to": "analyse"},
        "groups_removed": [world["a"]],
    }
    assert events[0]["actor_id"] == world["root"].user_id


# --- Affectation ---


def _assign(client: TestClient, dossier_id: str, person: RequestContext | None):
    return client.put(f"/api/dossiers/{dossier_id}/assignee", json={"assignee_id": person.user_id if person else None})


def test_one_can_only_assign_someone_who_has_access(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)  # /a seulement
        refused = _assign(client, dossier["id"], world["bob"])
        accepted = _assign(client, dossier["id"], world["carol"])

    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "assignee_has_no_access"
    assert accepted.status_code == 200 and accepted.json()["assignee"]["id"] == world["carol"].user_id


def test_bulk_assignment_is_all_or_nothing_on_access(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        open_to_all = _create(client, analyse, visibility="analyse")
        only_a = _create(client, analyse)
        response = client.put(
            "/api/dossiers/bulk-assignee",
            json={"dossier_ids": [open_to_all["id"], only_a["id"]], "assignee_id": world["bob"].user_id},
        )

    assert response.status_code == 422
    assert response.json()["detail"]["dossier_ids"] == [only_a["id"]]
    with As(world["root"]):
        assert client.get(f"/api/dossiers/{open_to_all['id']}").json()["assignee"] is None


def test_bulk_assignment_does_not_reveal_invisible_dossiers(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
    with As(world["bob"]):
        response = client.put("/api/dossiers/bulk-assignee", json={"dossier_ids": [dossier["id"]], "assignee_id": None})

    assert response.status_code == 404 and response.json()["detail"]["dossier_ids"] == [dossier["id"]]


def test_opening_the_dossier_keeps_its_assignee(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
        _assign(client, dossier["id"], world["alice"])
    with As(world["root"]):
        result = _put_access(client, dossier["id"], "analyse", [])  # plus de groupe, mais ouvert à l'analyse

    assert result.json()["assignee_unassigned"] is False
    with As(world["root"]):
        assert client.get(f"/api/dossiers/{dossier['id']}").json()["assignee"]["id"] == world["alice"].user_id


def test_an_assignee_who_loses_the_group_is_unassigned_and_it_is_traced(
    client: TestClient, analyse: dict, world: dict
) -> None:
    only_b_person = _person("dave", [world["b"]])
    with As(only_b_person):
        client.get("/api/auth/me")
    with As(world["bob"]):
        dossier = _create(client, analyse)  # /b
        _assign(client, dossier["id"], only_b_person)
    with As(world["root"]):
        _put_access(client, dossier["id"], "restricted", [world["b"], world["a"]])
        result = _put_access(client, dossier["id"], "restricted", [world["a"]]).json()
        events = _events(client, dossier["id"], "assignee_changed")

    assert result["assignee_unassigned"] is True
    assert events[0]["payload"]["reason"] == "access_lost" and events[0]["payload"]["to"] is None
    with As(world["root"]):
        assert client.get(f"/api/dossiers/{dossier['id']}").json()["assignee"] is None


def test_the_directory_remembers_groups_at_login(client: TestClient, analyse: dict, world: dict) -> None:
    """Une personne qui change de groupe est reprise à sa prochaine connexion : l'affectation suit l'annuaire."""
    moved = _person("moved", [world["b"]])
    with As(moved):
        client.get("/api/auth/me")
    with As(world["alice"]):
        dossier = _create(client, analyse)
        assert _assign(client, dossier["id"], moved).status_code == 422

    moved_now = RequestContext(**{**moved.__dict__, "groups": [world["a"]]})
    with As(moved_now):
        client.get("/api/auth/me")
    with As(world["alice"]):
        assert _assign(client, dossier["id"], moved).status_code == 200


# --- Simulation, lot, visibilité exposée (interface « Accès ») ---


def test_dry_run_names_who_would_lose_access_without_changing_anything(
    client: TestClient, analyse: dict, world: dict
) -> None:
    only_b = _person("dave", [world["b"]])
    with As(only_b):
        client.get("/api/auth/me")
    with As(world["bob"]):
        dossier = _create(client, analyse)  # /b
        _assign(client, dossier["id"], only_b)
    with As(world["root"]):
        client.put(
            f"/api/dossiers/{dossier['id']}/access",
            json={"visibility": "restricted", "group_paths": [world["b"], world["a"]]},
        )

        preview = client.put(
            f"/api/dossiers/{dossier['id']}/access",
            params={"dry_run": "true"},
            json={"visibility": "restricted", "group_paths": [world["a"]]},
        ).json()
        after = client.get(f"/api/dossiers/{dossier['id']}").json()
        events = _events(client, dossier["id"], "access_changed")

    assert preview["assignee_unassigned"] is True and preview["unassigned_person"]["id"] == only_b.user_id
    assert {g["path"] for g in preview["groups"]} == {world["a"], world["b"]}  # rien n'est enregistré
    assert after["assignee"]["id"] == only_b.user_id
    assert len(events) == 1  # seul le vrai changement est tracé, pas la simulation


def test_the_real_change_reports_the_person_it_unassigned(client: TestClient, analyse: dict, world: dict) -> None:
    only_b = _person("erin", [world["b"]])
    with As(only_b):
        client.get("/api/auth/me")
    with As(world["bob"]):
        dossier = _create(client, analyse)
        _assign(client, dossier["id"], only_b)
    with As(world["root"]):
        client.put(
            f"/api/dossiers/{dossier['id']}/access",
            json={"visibility": "restricted", "group_paths": [world["b"], world["a"]]},
        )
        result = _put_access(client, dossier["id"], "restricted", [world["a"]]).json()

    assert result["unassigned_person"]["id"] == only_b.user_id


def _bulk_access(client: TestClient, ids: list[str], visibility: str, groups: list[str]):
    return client.put(
        "/api/dossiers/bulk-access", json={"dossier_ids": ids, "visibility": visibility, "group_paths": groups}
    )


def test_bulk_access_replaces_the_groups_of_every_dossier(client: TestClient, analyse: dict, world: dict) -> None:
    with As(world["alice"]):
        first, second = _create(client, analyse), _create(client, analyse)
    with As(world["root"]):
        result = _bulk_access(client, [first["id"], second["id"], second["id"]], "analyse", [])
        listed = [client.get(f"/api/dossiers/{d['id']}").json()["visibility"] for d in (first, second)]
        again = _bulk_access(client, [first["id"], second["id"]], "analyse", [])

    assert result.status_code == 200 and result.json() == {"updated": 2, "unchanged": 0, "unassigned": 0}
    assert listed == ["analyse", "analyse"]
    assert again.json() == {"updated": 0, "unchanged": 2, "unassigned": 0}


def test_bulk_access_is_reserved_to_administrators_and_all_or_nothing(
    client: TestClient, analyse: dict, world: dict
) -> None:
    with As(world["alice"]):
        dossier = _create(client, analyse)
        assert _bulk_access(client, [dossier["id"]], "analyse", []).status_code == 403
    with As(world["root"]):
        ghost = str(uuid.uuid4())
        missing = _bulk_access(client, [dossier["id"], ghost], "analyse", [])
        foreign = _bulk_access(client, [dossier["id"]], "restricted", [world["b"]])
        empty = _bulk_access(client, [dossier["id"]], "restricted", [])
        still = client.get(f"/api/dossiers/{dossier['id']}").json()["visibility"]

    assert missing.status_code == 404 and missing.json()["detail"]["dossier_ids"] == [ghost]
    assert foreign.status_code == 422 and foreign.json()["detail"]["code"] == "group_not_yours"
    assert empty.status_code == 422 and empty.json()["detail"]["code"] == "groups_required"
    assert still == "restricted"  # rien n'a changé


def test_bulk_access_unassigns_people_who_lose_access(client: TestClient, analyse: dict, world: dict) -> None:
    only_b = _person("fred", [world["b"]])
    with As(only_b):
        client.get("/api/auth/me")
    with As(world["bob"]):
        dossier = _create(client, analyse)
        _assign(client, dossier["id"], only_b)
    with As(world["root"]):
        client.put(
            f"/api/dossiers/{dossier['id']}/access",
            json={"visibility": "restricted", "group_paths": [world["b"], world["a"]]},
        )
        result = _bulk_access(client, [dossier["id"]], "restricted", [world["a"]]).json()

    assert result == {"updated": 1, "unchanged": 0, "unassigned": 1}


def test_the_visibility_is_exposed_by_the_dossier_and_the_tracking(
    client: TestClient, analyse: dict, world: dict
) -> None:
    with As(world["alice"]):
        restricted = _create(client, analyse)
        open_one = _create(client, analyse, visibility="analyse")
        detail = client.get(f"/api/dossiers/{restricted['id']}").json()
        rows = client.get("/api/tracking", params={"analyse_id": analyse["id"], "page_size": 100}).json()["items"]
        only_restricted = client.get(
            "/api/tracking", params={"analyse_id": analyse["id"], "access": "restricted"}
        ).json()["items"]
        only_open = client.get("/api/tracking", params={"analyse_id": analyse["id"], "access": "analyse"}).json()[
            "items"
        ]
        bad = client.get("/api/tracking", params={"access": "secret"})

    assert detail["visibility"] == "restricted"
    assert {r["id"]: r["visibility"] for r in rows} == {restricted["id"]: "restricted", open_one["id"]: "analyse"}
    assert [r["id"] for r in only_restricted] == [restricted["id"]] and [r["id"] for r in only_open] == [open_one["id"]]
    assert bad.status_code == 422
