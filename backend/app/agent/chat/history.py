"""L'historique du chat tel que le modèle le lit, et ce qu'on en tire (synthèses, notes, sources)."""

import json

NO_DECISION = "La personne n'a pas pris de décision pour cet appel."
TOOL_GONE = "Cet outil n'est plus disponible : l'appel n'a pas été exécuté."


def build_conversation_history(conversation: dict) -> list[dict]:
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


def last_user_message_id(conversation: dict) -> str | None:
    """Identifiant du message de l'utilisateur qui a déclenché cette réponse
    (source des propositions déposées)."""
    for msg in reversed(conversation.get("messages", [])):
        if msg.get("role") == "user":
            return msg.get("id")
    return None


# Taille maximale des notes injectées dans le prompt du chat (les plus récentes d'abord).
NOTES_CONTEXT_MAX_CHARS = 6000


def notes_for_prompt(notes: list[dict]) -> list[str]:
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


def extract_syntheses(dossier: dict) -> list[dict]:
    """Récupère les synthèses existantes (output des agents terminés)
    depuis les execution_steps du dossier."""
    syntheses: list[dict] = []
    for step in dossier.get("execution_steps", []):
        if step.get("kind") == "agent" and step.get("output"):
            syntheses.append({"label": step.get("label", "Agent"), "output": step["output"]})
    return syntheses


def sources_to_api(sources: list) -> list[dict]:
    """Convertit les ConsultedSource en dictionnaires pour l'API interne
    (MessageSourceIn : dossier_document_id, page_ids, excerpt)."""
    result: list[dict] = []
    for src in sources:
        result.append(
            {
                "dossier_document_id": src.dossier_document_id,
                "page_ids": src.page_ids,
                "excerpt": src.excerpt,
                "number": src.number,
                "char_ranges": [list(r) for r in src.char_ranges],
            }
        )
    return result
