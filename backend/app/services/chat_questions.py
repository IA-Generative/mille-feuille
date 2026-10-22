"""La réponse à une question à choix posée par l'assistant (outil `ask_user`).

Même principe que la confirmation d'un outil (voir `chat_tool_calls`) : la question est enregistrée avec le message de
l'assistant, la tâche s'est terminée, et la réponse de la personne devient le **résultat** de l'appel dans l'historique
du modèle. Elle se donne tant qu'aucun autre message n'a été envoyé ; ensuite la question est « sans réponse ».

Les réponses sont validées contre les options **enregistrées** (celles que la personne a vues), jamais contre ce que le
client prétend. Le texte libre reste une donnée de la personne : il est présenté au modèle comme une réponse, pas comme
une consigne."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_tool_call import ChatToolCall, ChatToolCallStatus
from app.repositories.chat_tool_call_repository import ChatToolCallRepository
from app.schemas.chat_tool_call import ASK_USER, QuestionAnswer
from app.services.chat_tool_calls import DecisionError


def _check(question: dict, answer: QuestionAnswer, number: int) -> None:
    labels = [option["label"] for option in question["options"]]
    if len(set(answer.selected)) != len(answer.selected) or any(label not in labels for label in answer.selected):
        raise DecisionError("option_inconnue", f"Question {number} : une option choisie n'a pas été proposée.")
    if len(answer.selected) > 1 and not question.get("multi_select"):
        raise DecisionError("choix_unique", f"Question {number} : une seule option peut être choisie.")
    if not answer.selected and not answer.other:
        raise DecisionError("reponse_vide", f"Question {number} : il faut choisir une option ou écrire une réponse.")


def _summary(questions: list[dict], answers: Sequence[QuestionAnswer]) -> str:
    lines = []
    for question, answer in zip(questions, answers, strict=True):
        parts = list(answer.selected) + ([f"Autre : « {answer.other} »"] if answer.other else [])
        lines.append(f"- {question['question']} → {' ; '.join(parts)}")
    return "Réponses de la personne :\n" + "\n".join(lines)


async def answer_question(
    db: AsyncSession, conversation_id: uuid.UUID, call_id: uuid.UUID, answers: Sequence[QuestionAnswer], *, user_id: str
) -> ChatToolCall:
    repository = ChatToolCallRepository(db)
    call = await repository.get(call_id)
    if call is None or call.conversation_id != conversation_id or call.tool_id != ASK_USER:
        raise DecisionError("demande_inconnue", "Cette question n'existe pas dans cette conversation.")
    if call.status != ChatToolCallStatus.PENDING:
        raise DecisionError(
            "deja_decidee", "Cette question a déjà reçu une réponse, ou a été laissée sans réponse.", conflict=True
        )
    questions = call.arguments.get("questions", [])
    if len(answers) != len(questions):
        raise DecisionError("reponses_incompletes", "Il faut répondre à toutes les questions.")
    for number, (question, answer) in enumerate(zip(questions, answers, strict=True), start=1):
        _check(question, answer, number)

    call.status = ChatToolCallStatus.EXECUTED
    call.result = _summary(questions, answers)
    call.decided_by = user_id
    call.decided_at = datetime.now(UTC)
    await db.commit()
    return call
