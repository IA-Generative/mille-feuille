import uuid

from fastapi.testclient import TestClient

from tests.access_support import As
from tests.test_agent_tools import add_agent
from tests.test_dossier_access import _create
from tests.tool_support import FakeLister, create_server, tool_id

INTERNAL = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


def analyse_with_tools(client: TestClient, tools: list[str]) -> dict:
    analyse = client.post("/api/analyses", json={"name": f"Chat {uuid.uuid4().hex[:6]}", "description": "T"}).json()
    assert add_agent(client, analyse["id"], tools).status_code == 201
    return analyse


def open_chat(client: TestClient, analyse: dict) -> tuple[str, str]:
    """Un dossier de l'analyse, visible de toute personne, et la conversation de la personne courante."""
    dossier = _create(client, analyse, visibility="analyse")
    conversation = client.post(f"/api/dossiers/{dossier['id']}/conversations").json()
    return dossier["id"], conversation["id"]


def tools_url(dossier_id: str, conversation_id: str) -> str:
    return f"/api/dossiers/{dossier_id}/conversations/{conversation_id}/tools"


def test_the_chat_offers_the_tools_of_the_analysis_agents_all_active_by_default(
    client: TestClient, lister: FakeLister
) -> None:
    server = create_server(client, visibility="all", tools=["rechercher_texte", "envoyer_courriel"])
    search, mail = tool_id(server, "rechercher_texte"), tool_id(server, "envoyer_courriel")
    analyse = analyse_with_tools(client, ["calculatrice", search, mail])
    dossier_id, conversation_id = open_chat(client, analyse)

    body = client.get(tools_url(dossier_id, conversation_id)).json()

    assert [t["id"] for t in body["tools"]] == ["calculatrice", search, mail]
    assert (body["excluded"], body["unavailable"]) == ([], [])
    by_id = {t["id"]: t for t in body["tools"]}
    assert by_id["calculatrice"]["kind"] == "internal" and by_id["calculatrice"]["server_name"] is None
    assert by_id[search]["kind"] == "mcp" and by_id[search]["server_name"] == server["name"]


def test_a_tool_that_modifies_data_is_flagged_so_the_menu_can_say_it_asks_for_confirmation(
    client: TestClient, lister: FakeLister
) -> None:
    server = create_server(client, visibility="all", tools=["rechercher_texte", "envoyer_courriel"])
    analyse = analyse_with_tools(client, [tool_id(server, "rechercher_texte"), tool_id(server, "envoyer_courriel")])
    dossier_id, conversation_id = open_chat(client, analyse)

    by_name = {t["name"]: t for t in client.get(tools_url(dossier_id, conversation_id)).json()["tools"]}

    assert by_name["rechercher_texte"]["side_effect"] is False
    assert by_name["envoyer_courriel"]["side_effect"] is True
    assert "given_to_model" not in by_name["envoyer_courriel"]  # plus de verrou : la personne confirme l'appel


def test_the_person_can_remove_tools_for_the_conversation(client: TestClient, lister: FakeLister) -> None:
    server = create_server(client, visibility="all")
    search = tool_id(server, "rechercher_texte")
    analyse = analyse_with_tools(client, ["calculatrice", "calcul_dates", search])
    dossier_id, conversation_id = open_chat(client, analyse)

    body = client.put(tools_url(dossier_id, conversation_id), json={"excluded": ["calcul_dates", search]}).json()

    assert body["excluded"] == ["calcul_dates", search]
    assert len(body["tools"]) == 3  # le menu continue de les montrer, désactivés
    assert client.get(tools_url(dossier_id, conversation_id)).json()["excluded"] == ["calcul_dates", search]
    assert client.put(tools_url(dossier_id, conversation_id), json={"excluded": []}).json()["excluded"] == []


def test_only_tools_of_the_analysis_can_be_removed_and_duplicates_are_dropped(client: TestClient) -> None:
    analyse = analyse_with_tools(client, ["calculatrice"])
    dossier_id, conversation_id = open_chat(client, analyse)

    body = client.put(
        tools_url(dossier_id, conversation_id),
        json={"excluded": ["calculatrice", "calculatrice", "fantome", str(uuid.uuid4())]},
    ).json()

    assert body["excluded"] == ["calculatrice"]


def test_a_tool_of_a_server_the_person_cannot_see_is_reported_not_offered(
    client: TestClient, lister: FakeLister, world: dict
) -> None:
    with As(world["alice"]):
        private = tool_id(create_server(client, visibility="private"), "rechercher_texte")
        analyse = analyse_with_tools(client, ["calculatrice", private])
        dossier_id, conversation_id = open_chat(client, analyse)
    with As(world["bob"]):
        conversation_id = client.post(f"/api/dossiers/{dossier_id}/conversations").json()["id"]

        body = client.get(tools_url(dossier_id, conversation_id)).json()

    assert [t["id"] for t in body["tools"]] == ["calculatrice"]
    assert body["unavailable"] == [private]


def test_a_conversation_is_personal(client: TestClient, world: dict) -> None:
    analyse = analyse_with_tools(client, ["calculatrice"])
    dossier_id, alice_conversation = open_chat(client, analyse)
    with As(world["bob"]):
        assert client.get(tools_url(dossier_id, alice_conversation)).status_code == 404
        assert client.put(tools_url(dossier_id, alice_conversation), json={"excluded": []}).status_code == 404


def test_a_dossier_the_person_cannot_see_answers_not_found(client: TestClient, world: dict) -> None:
    analyse = analyse_with_tools(client, ["calculatrice"])
    with As(world["alice"]):
        restricted = _create(client, analyse, visibility="restricted", groups=[world["a"]])
        conversation_id = client.post(f"/api/dossiers/{restricted['id']}/conversations").json()["id"]
    with As(world["bob"]):  # groupe b : ne voit pas ce dossier
        assert client.get(tools_url(restricted["id"], conversation_id)).status_code == 404


def test_a_dossier_without_analysis_has_no_tools(client: TestClient) -> None:
    dossier = _create(client, None, visibility="analyse")
    conversation_id = client.post(f"/api/dossiers/{dossier['id']}/conversations").json()["id"]

    body = client.get(tools_url(dossier["id"], conversation_id)).json()

    assert body == {"tools": [], "excluded": [], "unavailable": []}


def test_the_worker_receives_the_tools_to_give_the_model(client: TestClient, lister: FakeLister) -> None:
    server = create_server(client, visibility="all")
    search = tool_id(server, "rechercher_texte")
    analyse = analyse_with_tools(client, ["calculatrice", "calcul_dates", search])
    dossier_id, conversation_id = open_chat(client, analyse)
    client.put(tools_url(dossier_id, conversation_id), json={"excluded": ["calcul_dates"]})

    internal = client.get(f"/api/internal/conversations/{conversation_id}", headers=INTERNAL).json()

    assert internal["tool_ids"] == ["calculatrice", search]  # l'union de l'analyse, moins ce que la personne a retiré
