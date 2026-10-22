import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.knowledge_sources import get_knowledge_client
from app.services.knowledge.client import KnowledgeError
from app.services.knowledge.contract import Collection, LookupResult, MissingCollection
from tests.access_support import As
from tests.test_knowledge_sources import add
from tests.test_knowledge_sources import probe as probe  # noqa: F401  (fixture : vérification de connexion simulée)

INTERNAL = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


class FakeProvider:
    """Un fournisseur en mémoire : ses collections, celles qu'une personne ne voit pas, et un nom qui change."""

    def __init__(self) -> None:
        self.names = {"guide": "Guide des subventions", "circulaires": "Circulaires", "crpa": "CRPA"}
        self.forbidden: set[str] = set()
        self.down = False
        self.lookups: list[tuple[str, list[str]]] = []

    async def lookup(self, url, headers, ids) -> LookupResult:
        self.lookups.append((url, list(ids)))
        if self.down:
            raise KnowledgeError("unavailable")
        items = [
            Collection(id=i, name=self.names[i], document_count=3)
            for i in ids
            if i in self.names and i not in self.forbidden
        ]
        missing = [
            MissingCollection(id=i, reason="forbidden" if i in self.forbidden else "not_found")
            for i in ids
            if i not in self.names or i in self.forbidden
        ]
        return LookupResult(items=items, missing=missing)

    async def list_collections(self, url, headers, *, page, page_size, q):  # pragma: no cover (sondage d'ajout)
        from app.services.knowledge.contract import CollectionPage

        return CollectionPage(items=[], total=0, page=1, page_size=1)


@pytest.fixture
def provider():
    fake = FakeProvider()
    app.dependency_overrides[get_knowledge_client] = lambda: fake
    yield fake
    del app.dependency_overrides[get_knowledge_client]


def make_analyse(client: TestClient) -> str:
    return client.post("/api/analyses", json={"name": f"KB {uuid.uuid4().hex[:6]}", "description": "T"}).json()["id"]


def make_source(client: TestClient, **extra) -> str:
    return add(client, **extra).json()["id"]


def url(analyse_id: str, suffix: str = "") -> str:
    return f"/api/analyses/{analyse_id}/knowledge-collections{suffix}"


def put(client: TestClient, analyse_id: str, *refs: tuple[str, str]):
    return client.put(url(analyse_id), json={"collections": [{"source_id": s, "collection_id": c} for s, c in refs]})


def test_an_analyse_starts_without_collections(client: TestClient, provider: FakeProvider) -> None:
    assert client.get(url(make_analyse(client))).json() == {"collections": [], "versions": []}


def test_collections_are_chosen_with_the_name_given_by_the_provider(
    client: TestClient, provider: FakeProvider, probe
) -> None:
    analyse, source = make_analyse(client), make_source(client)

    response = put(client, analyse, (source, "guide"), (source, "circulaires"), (source, "guide"))

    assert response.status_code == 200, response.text
    body = response.json()
    assert [(c["collection_id"], c["name"], c["status"]) for c in body["collections"]] == [
        ("guide", "Guide des subventions", "available"),
        ("circulaires", "Circulaires", "available"),
    ]  # le doublon est retiré, l'ordre demandé est gardé
    assert body["collections"][0]["source_name"].startswith("Références")


def test_a_collection_that_does_not_exist_or_is_forbidden_is_refused_with_its_reason(
    client: TestClient, provider: FakeProvider, probe
) -> None:
    analyse, source = make_analyse(client), make_source(client)
    provider.forbidden = {"crpa"}

    response = put(client, analyse, (source, "guide"), (source, "crpa"), (source, "disparue"))

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "collections_refusees"
    assert {(c["collection_id"], c["reason"]) for c in detail["collections"]} == {
        ("crpa", "accès refusé"),
        ("disparue", "introuvable chez le fournisseur"),
    }
    assert client.get(url(analyse)).json()["collections"] == []  # rien n'a été enregistré


def test_a_source_the_person_cannot_see_is_refused(
    client: TestClient, provider: FakeProvider, probe, world: dict
) -> None:
    with As(world["alice"]):
        private = make_source(client)
    analyse = make_analyse(client)
    with As(world["bob"]):
        response = put(client, analyse, (private, "guide"))

    assert response.status_code == 422
    assert response.json()["detail"]["collections"][0]["reason"] == "source inaccessible ou qui ne répond pas"
    assert provider.lookups == []  # le fournisseur n'est même pas interrogé


def test_an_unreachable_provider_refuses_the_addition_without_breaking_the_request(
    client: TestClient, provider: FakeProvider, probe
) -> None:
    analyse, source = make_analyse(client), make_source(client)
    provider.down = True

    response = put(client, analyse, (source, "guide"))

    assert response.status_code == 422 and "inaccessible" in response.json()["detail"]["collections"][0]["reason"]


def test_every_change_is_a_version_that_can_be_restored(client: TestClient, provider: FakeProvider, probe) -> None:
    analyse, source = make_analyse(client), make_source(client)

    def versions(response) -> list[list[str]]:
        return [[c["collection_id"] for c in v["content"]] for v in response.json()["versions"]]

    first = put(client, analyse, (source, "guide"))
    second = put(client, analyse, (source, "guide"), (source, "circulaires"))
    unchanged = put(client, analyse, (source, "guide"), (source, "circulaires"))
    third = put(client, analyse, (source, "circulaires"))

    assert sorted(versions(first)) == [[]]  # l'état d'avant le premier choix : vide
    assert sorted(versions(second)) == [[], ["guide"]]
    assert versions(unchanged) == versions(second)  # rien à changer : pas de version inutile
    assert sorted(versions(third)) == [[], ["guide"], ["guide", "circulaires"]]

    oldest = next(v for v in third.json()["versions"] if [c["collection_id"] for c in v["content"]] == ["guide"])
    restored = client.post(url(analyse, f"/restore/{oldest['id']}"))

    assert restored.status_code == 200, restored.text
    assert [c["collection_id"] for c in restored.json()["collections"]] == ["guide"]
    assert len(restored.json()["versions"]) == 4  # la liste restaurée devient elle-même une version
    assert client.post(url(analyse, f"/restore/{uuid.uuid4()}")).status_code == 404


def test_a_collection_that_became_unavailable_is_flagged_and_can_be_kept_or_removed(
    client: TestClient, provider: FakeProvider, probe
) -> None:
    analyse, source = make_analyse(client), make_source(client)
    put(client, analyse, (source, "guide"), (source, "crpa"))
    provider.forbidden = {"crpa"}
    del provider.names["guide"]

    flagged = client.get(url(analyse)).json()["collections"]
    assert [(c["collection_id"], c["status"]) for c in flagged] == [("guide", "not_found"), ("crpa", "forbidden")]
    assert flagged[0]["name"] == "Guide des subventions"  # le nom enregistré reste affichable

    # Une collection déjà choisie reste acceptée : on peut modifier le reste de la liste sans la retirer.
    kept = put(client, analyse, (source, "guide"), (source, "crpa"), (source, "circulaires"))
    assert kept.status_code == 200, kept.text
    removed = put(client, analyse, (source, "circulaires"))
    assert [c["collection_id"] for c in removed.json()["collections"]] == ["circulaires"]


def test_the_state_is_the_one_seen_by_the_person_who_asks(
    client: TestClient, provider: FakeProvider, probe, world: dict
) -> None:
    with As(world["alice"]):
        shared = make_source(client, visibility="all")
        analyse = make_analyse(client)
        put(client, analyse, (shared, "guide"))
    provider.forbidden = {"guide"}  # bob n'y a pas droit chez le fournisseur

    with As(world["bob"]):
        assert client.get(url(analyse)).json()["collections"][0]["status"] == "forbidden"
    with As(world["alice"]):
        provider.forbidden = set()
        assert client.get(url(analyse)).json()["collections"][0]["status"] == "available"


def test_a_source_that_is_no_longer_visible_flags_its_collections(
    client: TestClient, provider: FakeProvider, probe, world: dict
) -> None:
    with As(world["alice"]):
        shared = make_source(client, visibility="all")
        analyse = make_analyse(client)
        put(client, analyse, (shared, "guide"))
        assert client.delete(f"/api/knowledge-sources/{shared}").status_code == 204
        collection = client.get(url(analyse)).json()["collections"][0]

    assert collection["status"] == "source_unavailable" and collection["name"] == "Guide des subventions"


def test_the_worker_reads_the_collections_of_the_analyse(client: TestClient, provider: FakeProvider, probe) -> None:
    analyse, source = make_analyse(client), make_source(client)
    put(client, analyse, (source, "guide"))

    internal = client.get(f"/api/internal/analyses/{analyse}", headers=INTERNAL).json()

    assert internal["knowledge_collections"] == [
        {"source_id": source, "collection_id": "guide", "name": "Guide des subventions"}
    ]


def test_at_most_fifty_collections_and_an_unknown_analyse_is_a_404(client: TestClient, provider: FakeProvider) -> None:
    analyse = make_analyse(client)
    too_many = [{"source_id": str(uuid.uuid4()), "collection_id": str(n)} for n in range(51)]

    assert client.put(url(analyse), json={"collections": too_many}).status_code == 422
    assert client.get(url(str(uuid.uuid4()))).status_code == 404
