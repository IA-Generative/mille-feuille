import uuid

import pytest
from fastapi.testclient import TestClient

from tests.access_support import As
from tests.tool_support import FakeLister, create_server, tool_id


def new_analyse(client: TestClient) -> str:
    return client.post("/api/analyses", json={"name": f"Outils {uuid.uuid4().hex[:6]}", "description": "T"}).json()[
        "id"
    ]


def add_agent(client: TestClient, analyse_id: str, tools: list[str]):
    return client.post(
        f"/api/analyses/{analyse_id}/agents", json={"name": "Agent", "prompt": "Fais X", "tools": tools, "output": True}
    )


def set_tools(client: TestClient, analyse_id: str, agent_id: str, tools: list[str]):
    return client.put(f"/api/analyses/{analyse_id}/agents/{agent_id}/tools", json={"tools": tools})


def agent_of(client: TestClient, analyse_id: str, agent_id: str) -> dict:
    return next(a for a in client.get(f"/api/analyses/{analyse_id}").json()["agents"] if a["id"] == agent_id)


def test_legacy_and_new_internal_ids_are_accepted_and_stored_as_given(client: TestClient) -> None:
    analyse_id = new_analyse(client)
    response = add_agent(client, analyse_id, ["calculatrice", "base_connaissances", "calcul_dates", "notes_internes"])

    assert response.status_code == 201
    assert response.json()["tools"] == ["calculatrice", "base_connaissances", "calcul_dates", "notes_internes"]


def test_duplicates_are_dropped_in_order(client: TestClient) -> None:
    analyse_id = new_analyse(client)
    assert add_agent(client, analyse_id, ["calculatrice", "recherche_web", "calculatrice"]).json()["tools"] == [
        "calculatrice",
        "recherche_web",
    ]


@pytest.mark.parametrize("bad", ["fantome", "not-a-uuid", str(uuid.uuid4())])
def test_an_unknown_tool_is_refused_with_its_identifier(client: TestClient, bad: str) -> None:
    response = add_agent(client, new_analyse(client), ["calculatrice", bad])

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "tools_refuses"
    assert detail["tools"] == [bad]


def test_a_tool_of_an_mcp_server_the_person_can_see_is_accepted(client: TestClient, lister: FakeLister) -> None:
    server = create_server(client, visibility="all")
    mcp_tool = tool_id(server, "rechercher_texte")

    response = add_agent(client, new_analyse(client), ["calculatrice", mcp_tool])

    assert response.status_code == 201
    assert response.json()["tools"] == ["calculatrice", mcp_tool]


def test_a_tool_of_a_private_server_is_refused_to_someone_else(
    client: TestClient, lister: FakeLister, world: dict
) -> None:
    with As(world["alice"]):
        mcp_tool = tool_id(create_server(client, visibility="private"), "rechercher_texte")
    analyse_id = new_analyse(client)

    with As(world["bob"]):
        response = add_agent(client, analyse_id, [mcp_tool])

    assert response.status_code == 422
    assert "serveur inaccessible" in response.json()["detail"]["message"]


def test_a_tool_the_owner_did_not_authorize_is_refused(client: TestClient, lister: FakeLister) -> None:
    server = create_server(client, visibility="all", tools=["rechercher_texte"])  # lire_article reste non autorisé

    response = add_agent(client, new_analyse(client), [tool_id(server, "lire_article")])

    assert response.status_code == 422
    assert "non autorisé" in response.json()["detail"]["message"]


def test_update_records_a_version_and_restore_brings_it_back(client: TestClient, lister: FakeLister) -> None:
    mcp_tool = tool_id(create_server(client, visibility="all"), "rechercher_texte")
    analyse_id = new_analyse(client)
    agent_id = add_agent(client, analyse_id, ["calculatrice"]).json()["id"]

    assert set_tools(client, analyse_id, agent_id, ["calculatrice", mcp_tool]).json()["tools"] == [
        "calculatrice",
        mcp_tool,
    ]
    agent = agent_of(client, analyse_id, agent_id)
    assert [v["content"] for v in agent["tools_versions"]] == [["calculatrice"]]

    restored = client.post(
        f"/api/analyses/{analyse_id}/agents/{agent_id}/tools/restore/{agent['tools_versions'][0]['id']}"
    ).json()
    assert restored["tools"] == ["calculatrice"]


def test_an_agent_keeps_a_tool_that_became_unavailable_and_can_still_be_edited(
    client: TestClient, lister: FakeLister
) -> None:
    server = create_server(client, visibility="all")
    mcp_tool = tool_id(server, "rechercher_texte")
    analyse_id = new_analyse(client)
    agent_id = add_agent(client, analyse_id, ["calculatrice", mcp_tool]).json()["id"]
    client.delete(f"/api/tool-servers/{server['id']}")  # le tool n'existe plus

    # L'agent le garde tant que la personne ne le retire pas : on peut modifier le reste.
    assert agent_of(client, analyse_id, agent_id)["tools"] == ["calculatrice", mcp_tool]
    kept = set_tools(client, analyse_id, agent_id, ["calculatrice", mcp_tool, "recherche_web"])
    assert kept.status_code == 200
    # ... mais on ne peut pas le rajouter ailleurs.
    assert add_agent(client, analyse_id, [mcp_tool]).status_code == 422
    # ... et la personne peut le retirer.
    assert set_tools(client, analyse_id, agent_id, ["calculatrice"]).json()["tools"] == ["calculatrice"]


def test_an_ephemeral_analysis_accepts_internal_tools_only(client: TestClient) -> None:
    def create(tools: list[str]):
        return client.post(
            "/api/ephemeral/analyses",
            json={"name": "E", "classification_prompt": "C", "agents": [{"name": "A", "prompt": "P", "tools": tools}]},
        )

    assert create(["calculatrice"]).status_code == 201
    assert create(["fantome"]).status_code == 422
