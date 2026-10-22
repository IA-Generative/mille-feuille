"""L'outil `ask_user` du chat : une question à choix posée à la personne, enregistrée puis répondue plus tard."""

import json
from types import SimpleNamespace as NS

from app import chat_graph
from app.ask_user import ASK_USER, INVALID, normalize_questions
from app.tasks import chat as chat_mod
from app.tools import AgentTools

QUESTION = {
    "question": "À quel service écrire ?",
    "header": "Service concerné par la demande",
    "options": [{"label": "Subventions", "description": "Le guichet"}, {"label": "Finances"}],
}


def tools(*, ask_user: bool = True) -> AgentTools:
    return AgentTools({"documents": [], "execution_steps": []}, ask_user=ask_user)


class ScriptedLLM:
    def __init__(self, steps: list[tuple[list[tuple[str, dict]], str]]) -> None:
        self.steps = list(steps)
        self.requests: list[dict] = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        calls, content = self.steps.pop(0)
        message = NS(
            content=content,
            tool_calls=[
                NS(id=f"call-{i}", function=NS(name=name, arguments=json.dumps(args)))
                for i, (name, args) in enumerate(calls)
            ]
            or None,
        )
        return NS(choices=[NS(message=message)])


def test_the_questions_are_cleaned_before_they_are_shown() -> None:
    cleaned = normalize_questions(
        {
            "questions": [
                QUESTION | {"multi_select": True},
                {"question": "Une seule option ?", "options": [{"label": "Oui"}]},  # pas un choix : écartée
                {"question": "  ", "options": [{"label": "a"}, {"label": "b"}]},  # sans intitulé : écartée
                {"question": "Doublons ?", "options": [{"label": "a"}, {"label": "a"}, {"label": "b"}, "c", "d", "e"]},
            ]
        }
    )

    assert [q["question"] for q in cleaned] == ["À quel service écrire ?", "Doublons ?"]
    assert cleaned[0]["header"] == "Service conc" and cleaned[0]["multi_select"] is True
    assert cleaned[0]["options"] == [
        {"label": "Subventions", "description": "Le guichet"},
        {"label": "Finances", "description": ""},
    ]
    assert [o["label"] for o in cleaned[1]["options"]] == ["a", "b", "c", "d"] and cleaned[1]["multi_select"] is False
    assert normalize_questions({"questions": "n'importe quoi"}) == [] and normalize_questions({}) == []


def test_only_the_chat_is_given_the_question_tool() -> None:
    assert ASK_USER in [d["function"]["name"] for d in tools().tool_definitions()]
    assert ASK_USER not in [d["function"]["name"] for d in tools(ask_user=False).tool_definitions()]
    assert "ask_user" in chat_graph._build_system_prompt([], [], can_ask_user=True)
    assert "ask_user" not in chat_graph._build_system_prompt([], [])


def test_the_chat_records_the_question_and_stops(monkeypatch) -> None:
    chat_tools = tools()
    llm = ScriptedLLM([([("ask_user", {"questions": [QUESTION]}), ("view_entities", {})], "Une précision.")])
    monkeypatch.setattr(chat_graph, "_client", lambda: llm)

    answer, _ = chat_graph.run_chat(conversation_history=[{"role": "user", "content": "Écris-leur"}], tools=chat_tools)

    assert answer == "Une précision." and len(llm.requests) == 1  # le modèle n'est pas relancé
    [call] = chat_tools.confirmation_batch  # les autres appels du tour sont écartés
    assert (call["tool_id"], call["status"], call["side_effect"], call["llm_call_id"]) == (
        ASK_USER,
        "pending",
        False,
        "call-0",
    )
    assert call["arguments"]["questions"][0]["options"][1]["label"] == "Finances"


def test_a_question_without_valid_choices_does_not_interrupt_the_chat(monkeypatch) -> None:
    chat_tools = tools()
    llm = ScriptedLLM(
        [
            ([("ask_user", {"questions": [{"question": "Seul ?", "options": [{"label": "a"}]}]})], ""),
            ([], "Je continue sans question."),
        ]
    )
    monkeypatch.setattr(chat_graph, "_client", lambda: llm)

    answer, _ = chat_graph.run_chat(conversation_history=[{"role": "user", "content": "x"}], tools=chat_tools)

    assert answer == "Je continue sans question." and chat_tools.confirmation_batch == []
    tool_message = next(m for m in llm.requests[1]["messages"] if m["role"] == "tool")
    assert tool_message["content"] == INVALID


def test_the_answer_of_the_person_is_the_result_of_the_question_in_the_history() -> None:
    conversation = {
        "messages": [
            {"id": "m1", "role": "user", "content": "Écris-leur", "tool_calls": []},
            {
                "id": "m2",
                "role": "assistant",
                "content": "Une précision.",
                "tool_calls": [
                    {
                        "id": "tc-1",
                        "llm_call_id": "call-0",
                        "function_name": ASK_USER,
                        "tool_id": ASK_USER,
                        "tool_name": ASK_USER,
                        "server_name": "",
                        "arguments": {"questions": [QUESTION]},
                        "status": "executed",
                        "result": "Réponses de la personne :\n- À quel service écrire ? → Finances",
                    }
                ],
            },
        ]
    }

    history = chat_mod._build_conversation_history(conversation)

    assert history[1]["tool_calls"][0]["function"]["name"] == ASK_USER
    assert history[2] == {
        "role": "tool",
        "tool_call_id": "call-0",
        "content": "Réponses de la personne :\n- À quel service écrire ? → Finances",
    }
