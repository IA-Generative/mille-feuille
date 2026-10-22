"""Tâche de réponse au chat (conversation).

Cette tâche est déposée sur la file agent_execution quand l'utilisateur
envoie un message dans le chat d'un dossier (POST /dossiers/{id}/conversations/
{cid}/messages). Elle :

1. Charge la conversation (historique des messages + modèle LLM).
2. Charge le dossier complet (pages, prédictions) pour construire les outils.
3. Récupère les synthèses existantes (ExecutionStep.output des agents).
4. Exécute le graphe LangGraph de chat avec streaming (tool_calls, tool_results
   déposés comme chat_events pour le frontend SSE).
5. Dépose le message assistant final (avec sources) via l'API interne.

Contrairement à la tâche run_agents qui s'exécute une fois au lancement du
dossier, cette tâche s'exécute à chaque message utilisateur : le graphe
reconstruit le contexte à partir de l'historique de la conversation.
"""

import json
import logging
import uuid

from app import api_client, usage
from app.agent_tool_set import build_extra_tools
from app.analysis_tools import AnalysisProposer
from app.celery_app import celery_app
from app.chat_graph import run_chat as run_chat_graph
from app.config import settings
from app.note_tools import NoteWriter
from app.tools import AgentTools

logger = logging.getLogger(__name__)


NO_DECISION = "La personne n'a pas pris de décision pour cet appel."
TOOL_GONE = "Cet outil n'est plus disponible : l'appel n'a pas été exécuté."


def _build_conversation_history(conversation: dict) -> list[dict]:
    """Construit l'historique des messages au format OpenAI (role + content)
    à partir de la conversation. Le dernier message est celui de
    l'utilisateur qui vient d'être envoyé. Un message qui a demandé des outils est rebâti tel que le modèle l'a émis,
    suivi d'un message `tool` par appel : résultat, refus ou « sans réponse »."""
    history: list[dict] = []
    for msg in conversation.get("messages", []):
        calls = msg.get("tool_calls") or []
        if msg["role"] != "assistant" or not calls:
            history.append({"role": msg["role"], "content": msg["content"]})
            continue
        history.append(
            {
                "role": "assistant",
                "content": msg["content"],
                "tool_calls": [
                    {
                        "id": call["llm_call_id"],
                        "type": "function",
                        "function": {"name": call["function_name"], "arguments": json.dumps(call["arguments"])},
                    }
                    for call in calls
                ],
            }
        )
        history.extend(
            {"role": "tool", "tool_call_id": call["llm_call_id"], "content": call.get("result") or NO_DECISION}
            for call in calls
        )
    return history


def _run_approved_calls(client, conversation: dict, tools: AgentTools, on_event) -> None:
    """Exécute les appels que la personne a autorisés, avec les arguments qu'elle a vus, et dépose leur résultat.
    Les appels du conversation sont mis à jour pour que l'historique les porte."""
    for msg in conversation.get("messages", []):
        for call in msg.get("tool_calls") or []:
            if call["status"] != "approved" or call.get("result"):
                continue
            name = call["function_name"]
            on_event("tool_call", {"tool_name": call["tool_name"], "arguments": call["arguments"]})
            result = tools.dispatch_tool(name, call["arguments"]) if tools.has_extra(name) else TOOL_GONE
            api_client.record_chat_tool_result(client, call["id"], result)
            on_event("tool_result", {"tool_name": call["tool_name"], "preview": result[:200]})
            call["status"], call["result"] = "executed", result


def _last_user_message_id(conversation: dict) -> str | None:
    """Identifiant du message de l'utilisateur qui a déclenché cette réponse
    (source des propositions déposées)."""
    for msg in reversed(conversation.get("messages", [])):
        if msg.get("role") == "user":
            return msg.get("id")
    return None


# Taille maximale des notes injectées dans le prompt du chat (les plus récentes d'abord).
NOTES_CONTEXT_MAX_CHARS = 6000


def _notes_for_prompt(notes: list[dict]) -> list[str]:
    """Contenu des notes internes, la plus récente d'abord, borné en taille."""
    selected: list[str] = []
    used = 0
    for note in notes:
        content = (note.get("content") or "").strip()
        if not content:
            continue
        if used + len(content) > NOTES_CONTEXT_MAX_CHARS:
            content = content[: max(0, NOTES_CONTEXT_MAX_CHARS - used)]
            if content:
                selected.append(content + "…")
            break
        selected.append(content)
        used += len(content)
    return selected


def _extract_syntheses(dossier: dict) -> list[dict]:
    """Récupère les synthèses existantes (output des agents terminés)
    depuis les execution_steps du dossier."""
    syntheses: list[dict] = []
    for step in dossier.get("execution_steps", []):
        if step.get("kind") == "agent" and step.get("output"):
            syntheses.append({"label": step.get("label", "Agent"), "output": step["output"]})
    return syntheses


def _sources_to_api(sources: list) -> list[dict]:
    """Convertit les ConsultedSource en dictionnaires pour l'API interne
    (MessageSourceIn : dossier_document_id, page_ids, excerpt)."""
    result: list[dict] = []
    for src in sources:
        result.append(
            {
                "dossier_document_id": src.dossier_document_id,
                "page_ids": src.page_ids,
                "excerpt": src.excerpt,
            }
        )
    return result


@celery_app.task(name="app.tasks.run_chat", bind=True)
def run_chat(self, conversation_id: str, dossier_id: str) -> None:
    usage.bind("run_chat", dossier_id=dossier_id)
    with api_client.get_client() as client:
        try:
            # 1. Charge la conversation (historique + modèle LLM).
            conversation = api_client.get_conversation(client, conversation_id)
            model = conversation.get("model")
            usage.bind("run_chat", user_id=conversation.get("user_id"), dossier_id=dossier_id)

            # 2. Charge le dossier complet (pages, prédictions, synthèses).
            dossier = api_client.get_dossier(client, dossier_id)
            proposer = AnalysisProposer(
                client=client,
                dossier_id=dossier_id,
                user_id=conversation.get("user_id", ""),
                model=model or settings.LLM_MODEL,
                source_message_id=_last_user_message_id(conversation),
            )
            note_writer = NoteWriter(client=client, dossier_id=dossier_id, user_id=conversation.get("user_id", ""))
            # Les outils que l'analyse autorise (ses agents), moins ceux que la personne a retirés : calculatrice,
            # dates, serveurs MCP, appelés en son nom. Un outil qui modifie des données est donné, mais son appel
            # attend l'accord de la personne (la tâche se termine, la décision relance le chat).
            extra = build_extra_tools(
                client,
                conversation.get("tool_ids", []),
                acting_user=conversation.get("user_id"),
                run_id=f"chat-{conversation_id}-{uuid.uuid4().hex[:8]}",
                confirm_side_effects=True,
            )
            tools = AgentTools(dossier, analysis=proposer, notes=note_writer, extra=extra, ask_user=True)

            # 3. Récupère les synthèses existantes et les notes internes du dossier.
            syntheses = _extract_syntheses(dossier)
            notes = _notes_for_prompt(api_client.list_dossier_notes(client, dossier_id))

            # Callback pour streamer les événements au frontend : chaque
            # tool_call/tool_result est déposé en base (chat_events) et
            # relayé au frontend via SSE.
            def on_event(kind: str, data: dict) -> None:
                try:
                    api_client.add_chat_event(client, conversation_id, kind=kind, data=data)
                except Exception:
                    logger.warning(
                        "Failed to emit chat event %s for conversation %s",
                        kind,
                        conversation_id,
                        exc_info=True,
                    )

            # Les appels que la personne vient d'autoriser s'exécutent avant que le modèle ne reprenne.
            _run_approved_calls(client, conversation, tools, on_event)
            history = _build_conversation_history(conversation)

            logger.info(
                "Starting chat for conversation %s (dossier %s, %d messages, %d syntheses)",
                conversation_id,
                dossier_id,
                len(history),
                len(syntheses),
            )

            # 4. Exécute le graphe de chat.
            answer, sources = run_chat_graph(
                conversation_history=history,
                tools=tools,
                syntheses=syntheses,
                model=model,
                on_event=on_event,
                notes=notes,
            )

            # 5. Dépose le message assistant final (avec sources).
            api_client.deposit_assistant_message(
                client,
                conversation_id,
                content=answer,
                sources=_sources_to_api(sources),
                tool_calls=tools.confirmation_batch,
            )

            # Émet l'événement done pour fermer le flux SSE côté frontend.
            api_client.add_chat_event(client, conversation_id, kind="done", data={})

            logger.info(
                "Chat completed for conversation %s: %d chars, %d sources",
                conversation_id,
                len(answer),
                len(sources),
            )

        except Exception as error:
            logger.exception(
                "Chat failed for conversation %s (dossier %s)",
                conversation_id,
                dossier_id,
            )
            # Émet un événement error pour informer le frontend.
            try:
                api_client.add_chat_event(
                    client,
                    conversation_id,
                    kind="error",
                    data={"message": str(error)},
                )
            except Exception:
                pass
            raise
