import uuid

from fastapi.testclient import TestClient

from tests.test_chat_tool_calls import call_in, chat, decide, deposit, internal_calls
from tests.test_chat_tool_calls import dispatched as dispatched  # noqa: F401  (fixture autouse de ce module aussi)

QUESTIONS = [
    {
        "question": "À quel service écrire ?",
        "header": "Service",
        "multi_select": False,
        "options": [{"label": "Subventions", "description": ""}, {"label": "Finances", "description": ""}],
    },
    {
        "question": "Quelles pièces joindre ?",
        "header": "Pièces",
        "multi_select": True,
        "options": [{"label": "RIB", "description": ""}, {"label": "Statuts", "description": ""}],
    },
]


def question_in(questions: list[dict] = QUESTIONS) -> dict:
    return {
        "llm_call_id": f"call_{uuid.uuid4().hex[:8]}",
        "function_name": "ask_user",
        "tool_id": "ask_user",
        "tool_name": "ask_user",
        "server_name": "",
        "arguments": {"questions": questions},
        "side_effect": False,
        "status": "pending",
    }


def answer(client: TestClient, dossier_id: str, conversation_id: str, call_id: str, answers: list[dict]):
    url = f"/api/dossiers/{dossier_id}/conversations/{conversation_id}/tool-calls/{call_id}/answer"
    return client.post(url, json={"answers": answers})


def asked(client: TestClient) -> tuple[str, str, str]:
    dossier_id, conversation_id = chat(client)
    [call] = deposit(client, conversation_id, [question_in()], content="Une précision ?")["tool_calls"]
    return dossier_id, conversation_id, call["id"]


def test_the_answers_become_the_result_of_the_question_and_the_chat_resumes(
    client: TestClient, dispatched: list
) -> None:
    dossier_id, conversation_id, call_id = asked(client)

    response = answer(
        client,
        dossier_id,
        conversation_id,
        call_id,
        [{"selected": ["Finances"]}, {"selected": ["RIB", "Statuts"], "other": "  et le PV  "}],
    )

    assert response.status_code == 200 and response.json()["status"] == "executed"
    assert dispatched == [(conversation_id, dossier_id)]
    [stored] = internal_calls(client, conversation_id)
    assert stored["result"] == (
        "Réponses de la personne :\n"
        "- À quel service écrire ? → Finances\n"
        "- Quelles pièces joindre ? → RIB ; Statuts ; Autre : « et le PV »"
    )


def test_a_free_text_alone_answers_a_question(client: TestClient) -> None:
    dossier_id, conversation_id, call_id = asked(client)

    response = answer(
        client, dossier_id, conversation_id, call_id, [{"other": "Le bureau des marchés"}, {"selected": ["RIB"]}]
    )

    assert response.status_code == 200
    assert "Autre : « Le bureau des marchés »" in internal_calls(client, conversation_id)[0]["result"]


def test_answers_are_checked_against_the_options_the_person_saw(client: TestClient, dispatched: list) -> None:
    dossier_id, conversation_id, call_id = asked(client)
    bad = {
        "option_inconnue": [{"selected": ["Cabinet"]}, {"selected": ["RIB"]}],
        "choix_unique": [{"selected": ["Finances", "Subventions"]}, {"selected": ["RIB"]}],
        "reponse_vide": [{"selected": []}, {"selected": ["RIB"]}],
        "reponses_incompletes": [{"selected": ["Finances"]}],
    }

    for code, answers in bad.items():
        response = answer(client, dossier_id, conversation_id, call_id, answers)
        assert response.status_code == 422 and response.json()["detail"]["code"] == code

    assert dispatched == [] and internal_calls(client, conversation_id)[0]["status"] == "pending"


def test_a_question_is_answered_once_and_not_after_another_message(client: TestClient, dispatched: list) -> None:
    dossier_id, conversation_id, call_id = asked(client)
    good = [{"selected": ["Finances"]}, {"selected": ["RIB"]}]
    assert answer(client, dossier_id, conversation_id, call_id, good).status_code == 200

    assert answer(client, dossier_id, conversation_id, call_id, good).status_code == 409
    assert len(dispatched) == 1

    other_dossier, other_conversation, other_call = asked(client)
    client.post(
        f"/api/dossiers/{other_dossier}/conversations/{other_conversation}/messages", json={"content": "Autre chose"}
    )
    late = answer(client, other_dossier, other_conversation, other_call, good)
    assert late.status_code == 409 and internal_calls(client, other_conversation)[0]["status"] == "superseded"


def test_a_question_is_not_a_tool_decision(client: TestClient, dispatched: list) -> None:
    dossier_id, conversation_id, call_id = asked(client)

    response = decide(client, dossier_id, conversation_id, {call_id: True})

    assert response.status_code == 422 and response.json()["detail"]["code"] == "demande_inconnue"
    assert dispatched == []


def test_only_the_author_answers_and_only_a_question(client: TestClient) -> None:
    dossier_id, conversation_id, call_id = asked(client)
    [tool_call] = deposit(client, conversation_id, [call_in("a")])["tool_calls"]

    not_a_question = answer(client, dossier_id, conversation_id, tool_call["id"], [{"other": "x"}])

    assert not_a_question.status_code == 422 and not_a_question.json()["detail"]["code"] == "demande_inconnue"
    assert answer(client, dossier_id, str(uuid.uuid4()), call_id, [{"other": "x"}]).status_code == 404
