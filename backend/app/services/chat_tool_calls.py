"""La décision d'un lot d'appels d'outils du chat. Le modèle a demandé jusqu'à 5 appels dans un même tour ; la personne
les décide **tous ensemble** (une carte, un onglet par demande, une validation) : le protocole du modèle exige une
réponse pour chaque appel avant de pouvoir reprendre.

Une demande ne se décide que **tant qu'aucun autre message n'a été envoyé** : écrire autre chose la fait passer à
« sans réponse » (voir `ChatToolCallRepository.supersede_pending`). L'historique d'une discussion ne change donc jamais
après coup."""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_tool_call import ChatToolCall, ChatToolCallStatus
from app.repositories.chat_tool_call_repository import ChatToolCallRepository
from app.schemas.chat_tool_call import ASK_USER, ToolCallDecision


class DecisionError(Exception):
    """La décision est refusée ; `code` est stable, `message` est affichable."""

    def __init__(self, code: str, message: str, *, conflict: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.conflict = conflict


async def decide_batch(
    db: AsyncSession, conversation_id: uuid.UUID, decisions: Sequence[ToolCallDecision], *, user_id: str
) -> list[ChatToolCall]:
    """Enregistre la décision de chaque demande du lot. Tout ou rien."""
    repository = ChatToolCallRepository(db)
    ids = [decision.id for decision in decisions]
    if len(set(ids)) != len(ids):
        raise DecisionError("decision_en_double", "Une demande ne peut être décidée qu'une fois.")
    calls = await repository.for_ids(conversation_id, ids)
    if len(calls) != len(ids) or any(call.tool_id == ASK_USER for call in calls):
        raise DecisionError("demande_inconnue", "Cette demande n'existe pas dans cette conversation.")
    if any(call.status != ChatToolCallStatus.PENDING for call in calls):
        raise DecisionError(
            "deja_decidee", "Cette demande a déjà reçu une réponse, ou a été laissée sans réponse.", conflict=True
        )
    if len({call.message_id for call in calls}) != 1:
        raise DecisionError("lots_differents", "Les demandes décidées doivent venir du même message.")
    # Le lot se décide en entier : il faut une réponse pour chaque demande encore en attente de ce message.
    still_pending = await repository.pending_of_message(calls[0].message_id)
    if {call.id for call in still_pending} != set(ids):
        raise DecisionError("lot_incomplet", "Il faut répondre à toutes les demandes de ce message.")

    by_id = {decision.id: decision for decision in decisions}
    for call in calls:
        decision = by_id[call.id]
        await repository.decide(call, allow=decision.allow, user_id=user_id, comment=decision.comment)
    await db.commit()
    return sorted(calls, key=lambda call: call.position)
