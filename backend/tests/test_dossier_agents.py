"""Les agents interrogeables dans le chat d'un dossier : ceux de son analyse, avec les droits de lecture du dossier."""

import uuid

from fastapi.testclient import TestClient

from tests.access_support import As
from tests.test_agent_tools import add_agent
from tests.test_dossier_access import _create


def new_analyse(client: TestClient) -> dict:
    return client.post("/api/analyses", json={"name": f"Agents {uuid.uuid4().hex[:6]}", "description": "T"}).json()


def agents_url(dossier_id: str) -> str:
    return f"/api/dossiers/{dossier_id}/agents"


def test_the_agents_of_the_analysis_are_listed_in_its_order_with_their_role(client: TestClient) -> None:
    analyse = new_analyse(client)
    for name, prompt in (("Juriste", "Tu analyses\nles clauses."), ("Comptable", "Tu vérifies les montants.")):
        client.post(
            f"/api/analyses/{analyse['id']}/agents", json={"name": name, "prompt": prompt, "tools": [], "output": True}
        )
    dossier = _create(client, analyse, visibility="analyse")

    response = client.get(agents_url(dossier["id"]))

    assert response.status_code == 200
    assert response.json() == [
        {"name": "Juriste", "role": "Tu analyses les clauses."},
        {"name": "Comptable", "role": "Tu vérifies les montants."},
    ]


def test_an_analysis_without_agent_lists_nothing(client: TestClient) -> None:
    dossier = _create(client, new_analyse(client), visibility="analyse")

    assert client.get(agents_url(dossier["id"])).json() == []


def test_a_dossier_without_analysis_lists_nothing(client: TestClient) -> None:
    dossier = _create(client, None, visibility="analyse")

    assert client.get(agents_url(dossier["id"])).json() == []


def test_a_dossier_the_person_cannot_see_does_not_reveal_its_agents(client: TestClient, world: dict) -> None:
    analyse = new_analyse(client)
    assert add_agent(client, analyse["id"], []).status_code == 201
    with As(world["alice"]):
        restricted = _create(client, analyse, visibility="restricted", groups=[world["a"]])
        assert len(client.get(agents_url(restricted["id"])).json()) == 1
    with As(world["bob"]):  # groupe b : ne voit pas ce dossier
        assert client.get(agents_url(restricted["id"])).status_code == 404
