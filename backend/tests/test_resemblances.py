import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import async_session_factory
from app.models.analyse import EntityDefinition, EntityType
from app.models.dossier_analysis import AnalysisElementKind, ElementVersionOrigin
from app.models.resemblance import ResemblanceDismissal, ResemblanceMember
from app.repositories.dossier_analysis_repository import DossierAnalysisRepository
from app.services.resemblance import compute, entity_index
from tests.access_support import As
from tests.test_dossier_search import _dossier, _word


@pytest.fixture(autouse=True)
def _compute_by_hand(monkeypatch):
    """Le calcul est lancé à la main par les tests, jamais en arrière-plan."""
    monkeypatch.setattr("app.routers.resemblances.dispatch_compute", lambda theme_id: None)
    monkeypatch.setenv("RESEMBLANCE_ENABLED", "true")


def _entity(client: TestClient, analyse: dict, name: str, definition: str = "") -> str:
    async def add() -> str:
        async with async_session_factory() as db:
            entity = EntityDefinition(
                analyse_id=uuid.UUID(analyse["id"]), name=name, definition=definition, type=EntityType.TEXTE
            )
            db.add(entity)
            await db.commit()
            return str(entity.id)

    return client.portal.call(add)


def _value(client: TestClient, dossier_id: str, entity_id: str, value: str) -> None:
    async def add() -> None:
        async with async_session_factory() as db:
            repository = DossierAnalysisRepository(db)
            analysis = await repository.get_current(uuid.UUID(dossier_id)) or await repository.create_analysis(
                uuid.UUID(dossier_id)
            )
            await repository.create_element(
                analysis,
                origin=ElementVersionOrigin.MODEL,
                kind=AnalysisElementKind.ENTITY,
                value={"value": value},
                definition_id=uuid.UUID(entity_id),
                definition_name="Nom",
            )

    client.portal.call(add)


def _criterion(*entity_ids: str, name: str = "Personne", key: str = "c1") -> dict:
    return {"id": key, "origin": "analysis", "name": name, "entity_ids": list(entity_ids)}


def _theme(client: TestClient, *criteria: dict, **body) -> dict:
    created = client.post("/api/resemblances/themes", json={"name": "Essai", "criteria": list(criteria), **body})
    assert created.status_code == 201, created.text
    return created.json()


def _compute(client: TestClient, theme: dict) -> None:
    async def run() -> None:
        async with async_session_factory() as db:
            await compute.compute_theme(db, uuid.UUID(theme["id"]))

    client.portal.call(run)


def _groups(client: TestClient, theme: dict, **params) -> dict:
    response = client.get(f"/api/resemblances/themes/{theme['id']}/groups", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _members(group: dict) -> list[str]:
    return sorted(d["id"] for d in group["dossiers"])


def test_equivalent_entities_group_dossiers_and_all_criteria_are_required(client, analyse) -> None:
    person, company = _word(), _word()
    demandeur = _entity(client, analyse, "Nom du demandeur")
    requerant = _entity(client, analyse, "Identité du requérant")
    employer = _entity(client, analyse, "Employeur")
    first, second, third = (_dossier(client, analyse) for _ in range(3))
    _value(client, first, demandeur, person)
    _value(client, second, requerant, person.upper())
    _value(client, third, demandeur, person)
    _value(client, first, employer, company)
    _value(client, second, employer, company)

    alone = _theme(client, _criterion(demandeur))
    both = _theme(client, _criterion(demandeur, requerant))
    combined = _theme(client, _criterion(demandeur, requerant), _criterion(employer, name="Employeur", key="c2"))
    for theme in (alone, both, combined):
        _compute(client, theme)

    # Sans équivalence, seule l'entité choisie est comparée.
    assert [_members(g) for g in _groups(client, alone)["items"]] == [sorted([first, third])]
    assert [_members(g) for g in _groups(client, both)["items"]] == [sorted([first, second, third])]
    [group] = _groups(client, combined)["items"]
    assert _members(group) == sorted([first, second])
    assert group["label"].casefold() == f"{person} + {company}".casefold()
    assert group["reason"] == "En commun : personne et employeur."
    assert {o["origin"] for o in group["occurrences"]} == {f"Analyse {analyse['name']} · Nom"}


def test_a_group_is_only_what_the_person_can_see_at_reading_time(client, world, analyse) -> None:
    value = _word()
    entity = _entity(client, analyse, "Nom")
    theme = _theme(client, _criterion(entity))
    with As(world["alice"]):
        mine = [_dossier(client, analyse, visibility="restricted", group_ids=[world["a"]]) for _ in range(2)]
    with As(world["bob"]):
        secret = _dossier(client, analyse, visibility="restricted", group_ids=[world["b"]])
    for dossier_id in [*mine, secret]:
        _value(client, dossier_id, entity, value)
    _compute(client, theme)

    with As(world["alice"]):
        response = client.get(f"/api/resemblances/themes/{theme['id']}/groups")
        assert [_members(g) for g in response.json()["items"]] == [sorted(mine)]
        assert secret not in response.text
    with As(world["bob"]):
        # Un seul dossier visible : le groupe n'est pas renvoyé.
        assert _groups(client, theme) == {"items": [], "total": 0, "page": 1, "page_size": 20}


def test_a_disabled_theme_or_computation_produces_nothing(client, analyse, monkeypatch) -> None:
    value = _word()
    entity = _entity(client, analyse, "Nom")
    for _ in range(2):
        _value(client, _dossier(client, analyse), entity, value)
    theme = _theme(client, _criterion(entity))
    _compute(client, theme)
    assert _groups(client, theme)["total"] == 1

    body = {"name": "Essai", "criteria": [_criterion(entity)], "active": False}
    assert client.put(f"/api/resemblances/themes/{theme['id']}", json=body).status_code == 200
    _compute(client, theme)
    assert _groups(client, theme)["total"] == 0

    assert client.put(f"/api/resemblances/themes/{theme['id']}", json={**body, "active": True}).status_code == 200
    monkeypatch.setenv("RESEMBLANCE_ENABLED", "false")
    _compute(client, theme)

    async def stored() -> int:
        async with async_session_factory() as db:
            rows = await db.scalars(
                select(ResemblanceMember).where(ResemblanceMember.theme_id == uuid.UUID(theme["id"]))
            )
            return len(list(rows))

    assert client.portal.call(stored) == 0
    assert client.get("/api/resemblances/themes").json()["enabled"] is False


def test_the_scope_across_analyse_themes_needs_two_of_them(client, analyse) -> None:
    value = _word()
    entity = _entity(client, analyse, "Nom")
    for _ in range(2):
        _value(client, _dossier(client, analyse), entity, value)
    within = _theme(client, _criterion(entity), scope="within")
    across = _theme(client, _criterion(entity), scope="across")
    for theme in (within, across):
        _compute(client, theme)

    assert (_groups(client, within)["total"], _groups(client, across)["total"]) == (1, 0)


def test_a_group_can_be_dismissed_and_restored_with_a_trace(client, analyse) -> None:
    value = _word()
    entity = _entity(client, analyse, "Nom")
    for _ in range(2):
        _value(client, _dossier(client, analyse), entity, value)
    theme = _theme(client, _criterion(entity))
    _compute(client, theme)
    key = _groups(client, theme)["items"][0]["key"]
    base = f"/api/resemblances/themes/{theme['id']}/groups/{key}"

    assert client.post(f"{base}/dismiss").status_code == 204
    # Un recalcul ne le fait pas revenir.
    _compute(client, theme)
    assert _groups(client, theme)["total"] == 0
    assert _groups(client, theme, dismissed=True)["items"][0]["dismissed"] is True
    assert client.post(f"{base}/restore").status_code == 204
    assert _groups(client, theme)["total"] == 1

    async def trace() -> list:
        async with async_session_factory() as db:
            rows = await db.scalars(
                select(ResemblanceDismissal).where(ResemblanceDismissal.theme_id == uuid.UUID(theme["id"]))
            )
            return [(row.dismissed_by is not None, row.restored_at is not None) for row in rows]

    assert client.portal.call(trace) == [(True, True)]


def test_only_administrators_define_themes_and_history_can_be_restored(client, world, analyse) -> None:
    entity = _entity(client, analyse, "Nom")
    theme = _theme(client, _criterion(entity))
    body = {"name": "Renommé", "criteria": [_criterion(entity)]}
    with As(world["alice"]):
        assert client.post("/api/resemblances/themes", json=body).status_code == 403
        assert client.get("/api/resemblances/entities").status_code == 403
        listed = {t["id"]: t for t in client.get("/api/resemblances/themes").json()["items"]}
        assert listed[theme["id"]]["versions"] == []

    updated = client.put(f"/api/resemblances/themes/{theme['id']}", json=body).json()
    assert [v["content"]["name"] for v in updated["versions"]] == ["Essai"]
    version = updated["versions"][0]["id"]
    restored = client.post(f"/api/resemblances/themes/{theme['id']}/versions/{version}/restore").json()
    assert (restored["name"], len(restored["versions"])) == ("Essai", 2)
    unknown = client.post("/api/resemblances/themes", json={**body, "criteria": [_criterion(str(uuid.uuid4()))]})
    assert unknown.status_code == 422
    assert client.delete(f"/api/resemblances/themes/{theme['id']}").status_code == 204


def test_without_a_vector_base_the_suggestions_say_so(client, monkeypatch) -> None:
    monkeypatch.setattr(entity_index, "available", lambda: False)

    response = client.post("/api/resemblances/entities/suggestions", json={"text": "numéro de permis"})

    assert response.json() == {"available": False, "items": []}


def test_similar_definitions_are_suggested(client, analyse, monkeypatch) -> None:
    from qdrant_client import QdrantClient

    from app.services.search import qdrant_store

    memory = QdrantClient(":memory:")
    monkeypatch.setattr(qdrant_store, "get_client", lambda: memory)
    monkeypatch.setattr(entity_index, "available", lambda: True)
    monkeypatch.setattr(entity_index, "model", lambda: "test-model")
    marker = _word()

    def vectors(texts, _model):
        # Les définitions qui parlent de la même personne vont dans la même direction.
        return [[1.0, 0.0] if marker in text else [0.0, 1.0] for text in texts]

    monkeypatch.setattr(entity_index, "embed_dense", vectors)
    demandeur = _entity(client, analyse, "Nom du demandeur", f"La personne {marker}")
    requerant = _entity(client, analyse, "Identité du requérant", f"La personne {marker}")

    found = client.post("/api/resemblances/entities/suggestions", json={"entity_ids": [demandeur]}).json()

    assert (found["available"], [e["id"] for e in found["items"]]) == (True, [requerant])
