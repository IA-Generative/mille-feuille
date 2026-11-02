"""Répondre à un message de l'assistant de l'application (issue #50).

Sur le modèle du chat d'un dossier, sans dossier à charger en amont : l'historique de la conversation suffit, les
dossiers et analyses sont découverts ou créés par les outils au fil de l'exécution. L'assistant agit au nom de la
personne qui a ouvert la conversation. Le travail se termine toujours par un événement `done` ou `error`."""

import logging
import uuid

from app.agent import usage
from app.agent.agent_loop import run_agent
from app.agent.helper.tools import HelperTools
from app.db import async_session_factory
from app.models.agent_chat_event import AgentChatEventKind
from app.models.agent_conversation import AgentMessageRole
from app.repositories.agent_conversation_repository import AgentConversationRepository
from app.schemas.agent_conversation import AgentMessageSourceIn

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es l'agent helper de mille-feuille. Tu aides l'utilisateur à retrouver ou \
créer des analyses et des dossiers, à y ajouter des fichiers et à lancer le pipeline \
d'instruction (classification, extraction, agents), en langage naturel.

Outils disponibles : recherche/liste/détail/création d'analyses, recherche/liste/détail/création \
de dossiers, lancement du pipeline sur un dossier, consultation de ses résultats.

Tu ne peux pas ajouter de fichiers toi-même (aucun outil pour ça) : si l'utilisateur veut \
analyser des documents, dis-lui de les déposer via le bouton d'ajout de fichiers de la modal une \
fois le dossier créé, puis de te redemander de lancer le pipeline.

Avant de créer une nouvelle analyse, cherche s'il en existe déjà une pertinente \
(search_analyses) et propose-la plutôt que d'en recréer une similaire. Sois concis. Quand tu \
donnes le résultat d'une action sur un dossier ou une analyse, mentionne son nom pour que \
l'utilisateur puisse le retrouver facilement."""


async def _emit(conversation_id: str, kind: str, data: dict) -> None:
    try:
        async with async_session_factory() as db:
            await AgentConversationRepository(db).add_chat_event(
                uuid.UUID(conversation_id), AgentChatEventKind(kind), data
            )
    except Exception:
        logger.warning("Événement %s non déposé (conversation %s)", kind, conversation_id, exc_info=True)


async def run_helper_chat(conversation_id: str, model: str | None = None) -> None:
    usage.bind("run_helper_chat")
    try:
        async with async_session_factory() as db:
            conversation = await AgentConversationRepository(db).get(uuid.UUID(conversation_id))
            if conversation is None:
                raise LookupError(f"Conversation {conversation_id} introuvable")
            created_by = conversation.created_by
            # Le dialogue seul : les appels d'outils déjà journalisés ne comptent pas, l'agent refait son raisonnement.
            history = [
                {"role": m.role.value, "content": m.content}
                for m in conversation.messages
                if m.role in (AgentMessageRole.USER, AgentMessageRole.ASSISTANT)
            ]
        usage.bind("run_helper_chat", user_id=created_by)
        tools = HelperTools(created_by)

        async def on_event(kind: str, data: dict) -> None:
            await _emit(conversation_id, kind, data)

        logger.info("Assistant : conversation %s (%d messages)", conversation_id, len(history))
        answer = await run_agent(prompt=SYSTEM_PROMPT, tools=tools, model=model, history=history, on_event=on_event)

        resources = tools.consulted_resources()
        async with async_session_factory() as db:
            repository = AgentConversationRepository(db)
            conversation = await repository.get(uuid.UUID(conversation_id))
            await repository.add_message(
                conversation,
                AgentMessageRole.ASSISTANT,
                content=answer,
                sources=[
                    AgentMessageSourceIn(
                        dossier_id=r.dossier_id, analyse_id=r.analyse_id, excerpt=r.excerpt
                    ).model_dump()
                    for r in resources
                ],
            )
        await _emit(conversation_id, "done", {})
        logger.info("Assistant : réponse de %d caractères, %d ressources", len(answer), len(resources))
    except Exception as error:
        logger.exception("Assistant en échec (conversation %s)", conversation_id)
        await _emit(conversation_id, "error", {"message": str(error)})
