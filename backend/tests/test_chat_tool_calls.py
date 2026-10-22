import uuid

import pytest
from fastapi.testclient import TestClient

from tests.access_support import As
from tests.test_conversation_tools import analyse_with_tools, open_chat

INTERNAL = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


@pytest.fixture(autouse=True)
def dispatched(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Les relances du chat, sans Celery."""
    sent: list[tuple] = []
    monkeypatch.setattr("app.routers.chat_tool_calls.dispatch_chat_response", lambda *args: sent.append(args))
    monkeypatch.setattr("app.routers.dossiers.dispatch_chat_response", lambda *args: sent.append(args))
    return sent


def call_in(name: str, *, status: str = "pending", result: str | None = None, side_effect: bool = True) -> dict:
    return {
        "llm_call_id": f"call_{uuid.uuid4().hex[:8]}",
        "function_name": f"mcp_1234_{name}",
        "tool_id": str(uuid.uuid4()),
        "tool_name": name,
        "server_name": "Annuaire",
        "arguments": {"destinataire": "service@example.gouv.fr", "objet": name},
        "side_effect": side_effect,
        "status": status,
        "result": result,
    }


def chat(client: TestClient) -> tuple[str, str]:
    return open_chat(client, analyse_with_tools(client, ["calculatrice"]))


def deposit(client: TestClient, conversation_id: str, calls: list[dict], content: str = "Je demande l'envoi.") -> dict:
    response = client.post(
        f"/api/internal/conversations/{conversation_id}/messages",
        json={"content": content, "tool_calls": calls},
        headers=INTERNAL,
    )
    assert response.status_code == 200, response.text
    return response.json()


def decide(client: TestClient, dossier_id: str, conversation_id: str, answers: dict[str, bool]):
    body = {"decisions": [{"id": call_id, "allow": allow} for call_id, allow in answers.items()]}
    return client.post(f"/api/dossiers/{dossier_id}/conversations/{conversation_id}/tool-calls/decisions", json=body)


def messages(client: TestClient, dossier_id: str, conversation_id: str) -> list[dict]:
    return client.get(f"/api/dossiers/{dossier_id}/conversations/{conversation_id}/messages").json()["items"]


def internal_calls(client: TestClient, conversation_id: str) -> list[dict]:
    conversation = client.get(f"/api/internal/conversations/{conversation_id}", headers=INTERNAL).json()
    return [call for message in conversation["messages"] for call in message["tool_calls"]]


def test_the_assistant_message_carries_the_requested_calls_for_the_person_to_see(client: TestClient) -> None:
    dossier_id, conversation_id = chat(client)
    deposited = deposit(client, conversation_id, [call_in("envoyer_courriel")])

    [shown] = deposited["tool_calls"]
    [listed] = messages(client, dossier_id, conversation_id)[-1]["tool_calls"]

    assert (shown["status"], listed["status"]) == ("pending", "pending")
    assert listed["tool_name"] == "envoyer_courriel" and listed["server_name"] == "Annuaire"
    assert listed["arguments"] == {"destinataire": "service@example.gouv.fr", "objet": "envoyer_courriel"}
    assert "result" not in listed and "llm_call_id" not in listed  # le brut reste côté worker


def test_a_batch_is_decided_all_at_once_and_the_chat_resumes_once(client: TestClient, dispatched: list) -> None:
    dossier_id, conversation_id = chat(client)
    first, second = deposit(client, conversation_id, [call_in("a"), call_in("b")])["tool_calls"]

    response = decide(client, dossier_id, conversation_id, {first["id"]: True, second["id"]: False})

    assert response.status_code == 200
    assert [c["status"] for c in response.json()] == ["approved", "refused"]
    assert dispatched == [(conversation_id, dossier_id)]  # une seule relance pour tout le lot
    by_name = {c["tool_name"]: c for c in internal_calls(client, conversation_id)}
    assert by_name["a"]["status"] == "approved" and by_name["a"]["result"] is None  # le worker l'exécutera
    assert by_name["b"]["status"] == "refused" and "refusé" in by_name["b"]["result"]


def test_a_refusal_carries_what_the_person_wants_instead(client: TestClient, dispatched: list) -> None:
    dossier_id, conversation_id = chat(client)
    first, second = deposit(client, conversation_id, [call_in("a"), call_in("b")])["tool_calls"]
    decisions = [
        {"id": first["id"], "allow": False, "comment": "  Écris plutôt au service des finances.  "},
        {"id": second["id"], "allow": True, "comment": "ignoré pour une autorisation"},
    ]

    response = client.post(
        f"/api/dossiers/{dossier_id}/conversations/{conversation_id}/tool-calls/decisions",
        json={"decisions": decisions},
    )

    assert response.status_code == 200
    by_name = {c["tool_name"]: c for c in internal_calls(client, conversation_id)}
    assert by_name["a"]["result"].endswith("Elle précise : « Écris plutôt au service des finances. »")
    assert by_name["b"]["status"] == "approved" and by_name["b"]["result"] is None
    too_long = [{"id": first["id"], "allow": False, "comment": "x" * 501}]
    assert (
        client.post(
            f"/api/dossiers/{dossier_id}/conversations/{conversation_id}/tool-calls/decisions",
            json={"decisions": too_long},
        ).status_code
        == 422
    )


def test_every_pending_call_of_the_message_must_be_answered(client: TestClient, dispatched: list) -> None:
    dossier_id, conversation_id = chat(client)
    first, _second = deposit(client, conversation_id, [call_in("a"), call_in("b")])["tool_calls"]

    response = decide(client, dossier_id, conversation_id, {first["id"]: True})

    assert response.status_code == 422 and response.json()["detail"]["code"] == "lot_incomplet"
    assert dispatched == []
    assert {c["status"] for c in internal_calls(client, conversation_id)} == {"pending"}  # rien n'a bougé


def test_a_decision_cannot_be_replayed(client: TestClient, dispatched: list) -> None:
    dossier_id, conversation_id = chat(client)
    [call] = deposit(client, conversation_id, [call_in("a")])["tool_calls"]
    assert decide(client, dossier_id, conversation_id, {call["id"]: True}).status_code == 200

    again = decide(client, dossier_id, conversation_id, {call["id"]: False})

    assert again.status_code == 409 and again.json()["detail"]["code"] == "deja_decidee"
    assert len(dispatched) == 1  # pas de seconde relance
    assert internal_calls(client, conversation_id)[0]["status"] == "approved"  # le « non » tardif n'a rien changé


def test_writing_another_message_leaves_the_pending_calls_without_an_answer(
    client: TestClient, dispatched: list
) -> None:
    dossier_id, conversation_id = chat(client)
    [call] = deposit(client, conversation_id, [call_in("a")])["tool_calls"]

    client.post(f"/api/dossiers/{dossier_id}/conversations/{conversation_id}/messages", json={"content": "Autre chose"})

    late = decide(client, dossier_id, conversation_id, {call["id"]: True})
    assert late.status_code == 409
    [stored] = internal_calls(client, conversation_id)
    assert stored["status"] == "superseded" and "n'a pas été fait" in stored["result"]


def test_unknown_duplicated_and_foreign_calls_are_refused(client: TestClient, world: dict) -> None:
    dossier_id, conversation_id = chat(client)
    [call] = deposit(client, conversation_id, [call_in("a")])["tool_calls"]

    unknown = decide(client, dossier_id, conversation_id, {str(uuid.uuid4()): True})
    twice = client.post(
        f"/api/dossiers/{dossier_id}/conversations/{conversation_id}/tool-calls/decisions",
        json={"decisions": [{"id": call["id"], "allow": True}, {"id": call["id"], "allow": False}]},
    )

    assert unknown.status_code == 422 and unknown.json()["detail"]["code"] == "demande_inconnue"
    assert twice.status_code == 422 and twice.json()["detail"]["code"] == "decision_en_double"
    with As(world["bob"]):  # la conversation est personnelle
        assert decide(client, dossier_id, conversation_id, {call["id"]: True}).status_code == 404


def test_a_read_only_call_of_the_same_turn_is_kept_executed_and_cannot_be_decided(client: TestClient) -> None:
    dossier_id, conversation_id = chat(client)
    read = call_in("trouver_service", status="executed", result="Service des subventions", side_effect=False)
    write = call_in("envoyer_courriel")
    deposited = deposit(client, conversation_id, [read, write])["tool_calls"]

    stored = {c["tool_name"]: c for c in internal_calls(client, conversation_id)}
    assert (stored["trouver_service"]["status"], stored["trouver_service"]["result"]) == (
        "executed",
        "Service des subventions",
    )
    only_write = decide(client, dossier_id, conversation_id, {deposited[1]["id"]: True})  # seule la demande en attente
    assert only_write.status_code == 200
    assert decide(client, dossier_id, conversation_id, {deposited[0]["id"]: True}).status_code == 409


def test_a_batch_is_capped_at_five_calls(client: TestClient) -> None:
    _dossier_id, conversation_id = chat(client)
    response = client.post(
        f"/api/internal/conversations/{conversation_id}/messages",
        json={"content": "x", "tool_calls": [call_in(f"t{i}") for i in range(6)]},
        headers=INTERNAL,
    )
    assert response.status_code == 422


def test_the_worker_records_the_result_of_an_approved_call_only(client: TestClient) -> None:
    dossier_id, conversation_id = chat(client)
    approved, refused, waiting = deposit(client, conversation_id, [call_in("a"), call_in("b"), call_in("c")])[
        "tool_calls"
    ]
    # « c » reste en attente : la décision d'un lot exige toutes les demandes, on dépose donc un second message
    decide(client, dossier_id, conversation_id, {approved["id"]: True, refused["id"]: False, waiting["id"]: False})

    def result(call_id: str, text: str = "Courriel envoyé (REF-1)"):
        return client.post(f"/api/internal/chat-tool-calls/{call_id}/result", json={"result": text}, headers=INTERNAL)

    assert result(approved["id"]).status_code == 200
    assert result(refused["id"]).status_code == 409  # un appel refusé ne s'exécute jamais
    assert result(str(uuid.uuid4())).status_code == 404
    assert result(approved["id"]).status_code == 409  # déjà exécuté
    stored = {c["tool_name"]: c for c in internal_calls(client, conversation_id)}
    assert (stored["a"]["status"], stored["a"]["result"]) == ("executed", "Courriel envoyé (REF-1)")


def test_a_pending_call_cannot_be_executed_before_it_is_approved(client: TestClient) -> None:
    _dossier_id, conversation_id = chat(client)
    [call] = deposit(client, conversation_id, [call_in("a")])["tool_calls"]

    response = client.post(f"/api/internal/chat-tool-calls/{call['id']}/result", json={"result": "x"}, headers=INTERNAL)

    assert response.status_code == 409
    assert internal_calls(client, conversation_id)[0]["status"] == "pending"


def test_the_internal_routes_need_the_worker_token(client: TestClient) -> None:
    assert client.post(f"/api/internal/chat-tool-calls/{uuid.uuid4()}/result", json={"result": "x"}).status_code == 422
    bad = {"X-App-Token": "nope"}
    assert (
        client.post(
            f"/api/internal/chat-tool-calls/{uuid.uuid4()}/result", json={"result": "x"}, headers=bad
        ).status_code
        == 401
    )
