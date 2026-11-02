"""La conversation du chat telle que l'agent la lit, et le message qu'il y dépose."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import MessageRole
from app.models.message_external_source import MessageExternalSource
from app.repositories.analyse_repository import AnalyseRepository
from app.repositories.chat_tool_call_repository import ChatToolCallRepository
from app.repositories.dossier_repository import DossierRepository
from app.schemas.dossier import InternalConversationOut, InternalMessageIn
from app.services.tools.conversation_tools import tool_ids_for_chat


async def load_chat_conversation(db: AsyncSession, conversation_id: uuid.UUID) -> InternalConversationOut | None:
    """La conversation avec son historique, son modèle et les outils à donner au modèle : ceux que l'analyse autorise
    (ses agents), moins ceux que la personne a retirés pour cette conversation."""
    repository = DossierRepository(db)
    conversation = await repository.get_conversation(conversation_id)
    if conversation is None:
        return None
    out = InternalConversationOut.model_validate(conversation)
    dossier = await repository.get(conversation.dossier_id)
    analyse = await AnalyseRepository(db).get(dossier.analyse_id) if dossier and dossier.analyse_id else None
    if analyse is not None:
        out.tool_ids = tool_ids_for_chat(analyse, conversation.excluded_tools)
    return out


async def deposit_assistant_message(db: AsyncSession, conversation_id: uuid.UUID, body: InternalMessageIn):  # noqa: ANN201
    """Ajoute la réponse de l'assistant (avec ses sources, ses appels d'outils et les sources de la base de
    connaissances). None si la conversation n'existe plus."""
    repository = DossierRepository(db)
    conversation = await repository.get_conversation(conversation_id)
    if conversation is None:
        return None
    conversation = await repository.add_message(
        conversation,
        MessageRole.ASSISTANT,
        body.content,
        sources=[s.model_dump() for s in body.sources],
    )
    message = conversation.messages[-1]
    if body.external_sources:
        for position, source in enumerate(body.external_sources):
            message.external_sources.append(MessageExternalSource(position=position, **source.model_dump()))
        await db.commit()
        await db.refresh(message, attribute_names=["external_sources"])
    if body.tool_calls:
        await ChatToolCallRepository(db).add_batch(
            conversation_id=conversation_id,
            message_id=message.id,
            calls=[call.model_dump() for call in body.tool_calls],
        )
        await db.refresh(message, attribute_names=["tool_calls"])
    if body.execution is not None:
        message.execution = body.execution.model_dump(mode="json")
        await db.commit()
        await db.refresh(message)
    message.feedback = None
    return message
