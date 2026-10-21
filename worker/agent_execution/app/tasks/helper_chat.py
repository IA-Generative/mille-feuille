"""Tâche de réponse de l'agent helper (issue #50).

Déposée sur la file agent_execution quand l'utilisateur envoie un message
dans la modal de l'agent helper (POST /agent-conversations/{id}/messages),
ou par app/mcp/helper_server.py côté backend. Sur le modèle exact de
tasks/chat.py (chat par dossier), à ceci près qu'il n'y a pas de dossier à
charger en amont : l'historique de la conversation suffit, les
dossiers/analyses sont découverts/créés par les outils au fil de
l'exécution du graphe (voir app/helper_graph.py, app/helper_tools.py).
"""

import logging

from app import api_client, usage
from app.celery_app import celery_app
from app.helper_graph import run_helper_chat as run_helper_chat_graph
from app.helper_tools import ConsultedResource, HelperTools

logger = logging.getLogger(__name__)


def _build_conversation_history(conversation: dict) -> list[dict]:
    return [{"role": msg["role"], "content": msg["content"]} for msg in conversation.get("messages", [])]


def _resources_to_api(resources: list[ConsultedResource]) -> list[dict]:
    return [{"dossier_id": r.dossier_id, "analyse_id": r.analyse_id, "excerpt": r.excerpt} for r in resources]


@celery_app.task(name="app.tasks.run_helper_chat", bind=True)
def run_helper_chat(self, conversation_id: str, model: str | None = None) -> None:
    usage.bind("run_helper_chat")
    with api_client.get_client() as client:
        try:
            # 1. Charge la conversation (historique user/assistant).
            conversation = api_client.get_agent_conversation(client, conversation_id)
            # L'agent agit au nom de la personne qui a ouvert la conversation.
            api_client.act_for(client, conversation["created_by"])
            usage.bind("run_helper_chat", user_id=conversation["created_by"])
            history = _build_conversation_history(conversation)
            tools = HelperTools(client)

            def on_event(kind: str, data: dict) -> None:
                try:
                    api_client.add_agent_chat_event(client, conversation_id, kind=kind, data=data)
                except Exception:
                    logger.warning(
                        "Failed to emit agent chat event %s for conversation %s", kind, conversation_id, exc_info=True
                    )

            logger.info("Starting helper chat for conversation %s (%d messages)", conversation_id, len(history))

            # 2. Exécute le graphe de l'agent helper.
            answer, resources = run_helper_chat_graph(
                conversation_history=history, tools=tools, on_event=on_event, model=model
            )

            # 3. Dépose le message assistant final (avec les dossiers/analyses consultés/créés).
            api_client.deposit_agent_assistant_message(
                client, conversation_id, content=answer, sources=_resources_to_api(resources)
            )

            api_client.add_agent_chat_event(client, conversation_id, kind="done", data={})

            logger.info(
                "Helper chat completed for conversation %s: %d chars, %d resources",
                conversation_id,
                len(answer),
                len(resources),
            )

        except Exception as error:
            logger.exception("Helper chat failed for conversation %s", conversation_id)
            try:
                api_client.add_agent_chat_event(client, conversation_id, kind="error", data={"message": str(error)})
            except Exception:
                pass
            raise
