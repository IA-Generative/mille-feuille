import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.search_index import DossierSearchIndex, SearchIndexStatus
from app.services.search import settings as search_settings
from tests.document_helpers import run


@pytest.fixture(autouse=True)
def _platform_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARCH_EMBEDDING_MODEL", "bge-m3")
    monkeypatch.setenv("SEARCH_CHUNK_MODEL", "llama-decoupe")


def make_analyse(client: TestClient) -> str:
    return client.post("/api/analyses", json={"name": f"Recherche {uuid.uuid4().hex[:6]}", "description": "T"}).json()[
        "id"
    ]


def url(analyse_id: str, suffix: str = "") -> str:
    return f"/api/analyses/{analyse_id}/search-settings{suffix}"


def index_a_dossier(client: TestClient, analyse_id: str, status: SearchIndexStatus = SearchIndexStatus.READY) -> str:
    """Un dossier de l'analyse dont l'index a été construit avec les réglages actuels de l'analyse."""
    dossier_id = client.post("/api/dossiers", json={"name": "Dossier indexé", "analyse_id": analyse_id}).json()["id"]
    effective = client.get(url(analyse_id)).json()["effective"]

    async def add(session):
        session.add(
            DossierSearchIndex(
                dossier_id=uuid.UUID(dossier_id),
                fingerprint=search_settings.fingerprint(effective),
                settings=effective,
                status=status,
            )
        )
        await session.commit()

    run(client, add)
    return dossier_id


# --- Réglages et défauts ---


def test_an_analyse_starts_with_the_default_settings_resolved_with_the_platform_models(client: TestClient) -> None:
    body = client.get(url(make_analyse(client))).json()

    assert body["settings"] == {
        "strategy": "ia",
        "chunk_model": None,
        "size": 1000,
        "overlap": 150,
        "window": 1,
        "embedding_model": None,
    }
    assert body["effective"]["embedding_model"] == "bge-m3"
    assert body["effective"]["chunk_model"] == "llama-decoupe"
    assert body["fingerprint"] and body["problem"] is None
    assert body["versions"] == []
    assert body["overview"]["indexed"] == 0 and body["overview"]["obsolete"] == 0


def test_the_analyse_can_choose_its_own_models(client: TestClient) -> None:
    analyse = make_analyse(client)

    response = client.put(url(analyse), json={"strategy": "ia", "chunk_model": "gros-modele", "embedding_model": "e5"})

    assert response.status_code == 200, response.text
    assert response.json()["effective"]["chunk_model"] == "gros-modele"
    assert response.json()["effective"]["embedding_model"] == "e5"


def test_classic_chunking_keeps_size_overlap_and_window_and_needs_no_chunk_model(client: TestClient) -> None:
    analyse = make_analyse(client)

    response = client.put(
        url(analyse), json={"strategy": "classique", "size": 500, "overlap": 50, "window": 2, "embedding_model": "e5"}
    )

    effective = response.json()["effective"]
    assert (effective["strategy"], effective["size"], effective["overlap"], effective["window"]) == (
        "classique",
        500,
        50,
        2,
    )
    assert effective["chunk_model"] is None


def test_without_any_embedding_model_the_problem_is_reported(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_EMBEDDING_MODEL", "")
    body = client.get(url(make_analyse(client))).json()
    assert body["effective"] is None and body["fingerprint"] is None
    assert "embeddings" in body["problem"]


@pytest.mark.parametrize(
    "body",
    [
        {"strategy": "classique", "size": 100, "overlap": 100},
        {"strategy": "classique", "size": 50},
        {"strategy": "classique", "overlap": -1},
        {"strategy": "classique", "window": 9},
        {"strategy": "inconnue"},
    ],
)
def test_invalid_settings_are_refused(client: TestClient, body: dict) -> None:
    assert client.put(url(make_analyse(client)), json=body).status_code == 422


def test_an_unknown_analyse_is_a_404(client: TestClient) -> None:
    assert client.get(url(str(uuid.uuid4()))).status_code == 404


# --- Empreinte ---


def test_fingerprint_only_changes_with_what_changes_the_index() -> None:
    base = {
        "strategy": "classique",
        "chunk_model": None,
        "size": 500,
        "overlap": 50,
        "window": 1,
        "embedding_model": "m",
    }
    fingerprint = search_settings.fingerprint
    assert fingerprint(base) == fingerprint({**base, "window": 4})  # la fenêtre ne joue qu'à la recherche
    assert fingerprint(base) == fingerprint({**base, "chunk_model": "x"})  # sans effet en découpage classique
    assert fingerprint(base) != fingerprint({**base, "size": 600})
    assert fingerprint(base) != fingerprint({**base, "overlap": 60})
    assert fingerprint(base) != fingerprint({**base, "embedding_model": "autre"})
    ai = {**base, "strategy": "ia", "chunk_model": "c"}
    assert fingerprint(ai) == fingerprint({**ai, "size": 900, "overlap": 10})  # sans effet en découpage par IA
    assert fingerprint(ai) != fingerprint({**ai, "chunk_model": "d"})
    assert fingerprint(ai) != fingerprint(base)


# --- Historique et restauration ---


def test_every_change_keeps_the_previous_settings_and_they_can_be_restored(client: TestClient) -> None:
    analyse = make_analyse(client)
    client.put(url(analyse), json={"strategy": "classique", "size": 500, "overlap": 50})
    client.put(url(analyse), json={"strategy": "ia", "chunk_model": "c", "embedding_model": "e5"})

    body = client.get(url(analyse)).json()
    assert {v["content"]["strategy"] for v in body["versions"]} == {"classique", "ia"}
    classic = next(v for v in body["versions"] if v["content"]["strategy"] == "classique")

    restored = client.post(url(analyse, f"/restore/{classic['id']}"))

    assert restored.status_code == 200, restored.text
    assert restored.json()["settings"]["strategy"] == "classique"
    assert restored.json()["settings"]["size"] == 500
    assert len(restored.json()["versions"]) == 3  # l'état restauré a lui-même laissé une version


def test_saving_the_same_settings_twice_does_not_add_a_version(client: TestClient) -> None:
    analyse = make_analyse(client)
    client.put(url(analyse), json={"strategy": "classique"})
    client.put(url(analyse), json={"strategy": "classique"})
    assert len(client.get(url(analyse)).json()["versions"]) == 1


def test_restoring_an_unknown_version_is_a_404(client: TestClient) -> None:
    assert client.post(url(make_analyse(client), f"/restore/{uuid.uuid4()}")).status_code == 404


# --- Réglages modifiables après indexation ---


def test_settings_stay_editable_once_dossiers_are_indexed_and_they_become_obsolete(client: TestClient) -> None:
    analyse = make_analyse(client)
    client.put(url(analyse), json={"strategy": "classique", "embedding_model": "e5"})
    indexed = [index_a_dossier(client, analyse), index_a_dossier(client, analyse)]
    overview = client.get(url(analyse)).json()["overview"]
    assert (overview["indexed"], overview["current"], overview["obsolete"]) == (2, 2, 0)

    response = client.put(url(analyse), json={"strategy": "classique", "embedding_model": "autre"})

    assert response.status_code == 200, response.text
    overview = response.json()["overview"]
    assert (overview["indexed"], overview["current"], overview["obsolete"]) == (2, 0, 2)
    for dossier in indexed:  # l'index existant continue de servir
        state = client.get(f"/api/dossiers/{dossier}/search-index").json()
        assert state["freshness"] == "obsolete" and state["status"] == "ready"


def test_a_change_with_no_effect_on_the_index_obsoletes_nothing(client: TestClient) -> None:
    analyse = make_analyse(client)
    client.put(url(analyse), json={"strategy": "classique", "embedding_model": "e5", "window": 1})
    index_a_dossier(client, analyse)

    response = client.put(url(analyse), json={"strategy": "classique", "embedding_model": "e5", "window": 4})

    assert response.json()["overview"]["obsolete"] == 0


def test_restoring_earlier_settings_makes_the_matching_indexes_current_again(client: TestClient) -> None:
    analyse = make_analyse(client)
    client.put(url(analyse), json={"strategy": "classique", "embedding_model": "e5"})
    index_a_dossier(client, analyse)
    client.put(url(analyse), json={"strategy": "classique", "embedding_model": "autre"})
    version = client.get(url(analyse)).json()["versions"][0]["id"]

    restored = client.post(url(analyse, f"/restore/{version}"))

    assert restored.status_code == 200 and restored.json()["overview"]["obsolete"] == 0


def test_the_preview_says_what_a_change_would_cost_without_saving_it(client: TestClient) -> None:
    analyse = make_analyse(client)
    client.put(url(analyse), json={"strategy": "classique", "embedding_model": "e5"})
    index_a_dossier(client, analyse)
    index_a_dossier(client, analyse)

    preview = client.post(
        url(analyse, "/preview"), json={"strategy": "ia", "chunk_model": "c", "embedding_model": "e5"}
    )

    body = preview.json()
    assert preview.status_code == 200, preview.text
    assert (body["changes_index"], body["obsolete_dossiers"], body["indexed_dossiers"]) == (True, 2, 2)
    assert body["uses_ai_chunking"] is True and body["fingerprint"]
    assert client.get(url(analyse)).json()["settings"]["strategy"] == "classique"  # rien n'est enregistré


def test_the_preview_of_the_same_settings_changes_nothing(client: TestClient) -> None:
    analyse = make_analyse(client)
    client.put(url(analyse), json={"strategy": "classique", "embedding_model": "e5"})
    index_a_dossier(client, analyse)

    body = client.post(
        url(analyse, "/preview"), json={"strategy": "classique", "embedding_model": "e5", "window": 3}
    ).json()

    assert (body["changes_index"], body["obsolete_dossiers"], body["uses_ai_chunking"]) == (False, 0, False)


def test_the_preview_reports_incomplete_settings(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_EMBEDDING_MODEL", "")
    body = client.post(url(make_analyse(client), "/preview"), json={"strategy": "classique"}).json()
    assert body["effective"] is None and "embeddings" in body["problem"]
