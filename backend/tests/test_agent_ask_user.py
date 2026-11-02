"""L'outil `ask_user` du chat : une question à choix posée à la personne. (Son enregistrement par le chat est testé
avec le chat.)"""

from app.agent.ask_user import ASK_USER, normalize_questions
from app.agent.tools import AgentTools

QUESTION = {
    "question": "À quel service écrire ?",
    "header": "Service concerné par la demande",
    "options": [{"label": "Subventions", "description": "Le guichet"}, {"label": "Finances"}],
}


def tools(*, ask_user: bool = True) -> AgentTools:
    return AgentTools({"documents": [], "execution_steps": []}, ask_user=ask_user)


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
