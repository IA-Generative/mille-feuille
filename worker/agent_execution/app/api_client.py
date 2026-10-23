import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def get_client() -> httpx.Client:
    """Client HTTP authentifié vers le BFF, pour tous les appels à
    /api/internal/* (logs d'exécution, prédictions déposées, définitions
    de l'analyse...). Le jeton (voir app.core.security.internal.verify_app_token
    côté backend) est soit le secret de bootstrap fixe (dev local, docker-
    compose), soit le jeton en clair d'un AppToken créé via
    POST /api/app-tokens (prod, révocable indépendamment) - les deux
    marchent avec la même variable d'environnement, sans changement de
    code ici."""
    return httpx.Client(
        base_url=f"{settings.BACKEND_INTERNAL_URL}/api/internal",
        headers={"X-App-Token": settings.INTERNAL_WORKER_TOKEN},
        timeout=60.0,
    )


def act_for(client: httpx.Client, user_id: str) -> None:
    """Les appels suivants de ce client agissent **au nom de cette personne** (en-tête `X-Acting-User`) : l'agent
    assistant ne voit que les dossiers qu'elle voit (issue #222)."""
    client.headers["X-Acting-User"] = user_id


# --- Execution steps ---


def add_execution_log(client: httpx.Client, step_id: str, *, level: str = "info", message: str) -> dict:
    response = client.post(f"/execution-steps/{step_id}/logs", json={"level": level, "message": message})
    response.raise_for_status()
    return response.json()


def complete_execution_step(client: httpx.Client, step_id: str, *, status: str, output: str | None = None) -> dict:
    response = client.post(
        f"/execution-steps/{step_id}/complete",
        json={"status": status, "output": output},
    )
    response.raise_for_status()
    return response.json()


# --- Dossier & analyse definitions ---


def get_dossier(client: httpx.Client, dossier_id: str) -> dict:
    """Récupère le dossier avec ses documents, pages, et étapes d'exécution.
    Nécessite GET /internal/dossiers/{dossier_id} côté backend."""
    response = client.get(f"/dossiers/{dossier_id}")
    response.raise_for_status()
    return response.json()


def get_analyse_definitions(client: httpx.Client, analyse_id: str) -> dict:
    """Récupère les définitions de labels et d'entités de l'analyse, ainsi
    que les prompts de classification et d'extraction. Nécessite
    GET /internal/analyses/{analyse_id} côté backend."""
    response = client.get(f"/analyses/{analyse_id}")
    response.raise_for_status()
    return response.json()


# --- Predictions ---


# --- Analyse de dossier : unités de calcul ---
#
# L'analyse de dossier ne doit jamais faire échouer le pipeline : ces deux
# appels sont tolérants (journalisés, jamais levés). Un dossier sans analyse
# (exécution démarrée avant #125) répond 404 : le worker continue sans unité.


def reuse_agent_unit(client: httpx.Client, dossier_id: str, step_id: str) -> str | None:
    """Relance incrémentale (#119) : renvoie la synthèse de l'analyse précédente si
    l'agent de cette étape est inchangé (même configuration, mêmes entrées), sinon
    None (l'agent doit tourner). Tolérant : en cas d'erreur, l'agent tourne."""
    try:
        response = client.post(f"/dossiers/{dossier_id}/agent-units/reuse", json={"step_id": step_id})
        response.raise_for_status()
        data = response.json()
        return (data.get("output") or "") if data.get("reused") else None
    except Exception:
        logger.warning("Could not check agent reuse for step %s", step_id, exc_info=True)
        return None


# --- Analyse de dossier : consultation et propositions du chat ---


def get_current_analysis(client: httpx.Client, dossier_id: str) -> dict | None:
    """Analyse courante du dossier avec ses éléments, ou None si le dossier
    n'en a pas (exécution antérieure à l'analyse de dossier)."""
    response = client.get(f"/dossiers/{dossier_id}/analysis")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def create_proposal(client: httpx.Client, dossier_id: str, body: dict) -> dict:
    """Dépose une proposition de modification en attente (n'applique rien)."""
    response = client.post(f"/dossiers/{dossier_id}/analysis/proposals", json=body)
    response.raise_for_status()
    return response.json()


# --- Notes internes du dossier (issue #117) ---


def get_note(client: httpx.Client, note_id: str) -> dict:
    response = client.get(f"/notes/{note_id}")
    response.raise_for_status()
    return response.json()


def create_dossier_note(client: httpx.Client, dossier_id: str, content: str, author: str) -> dict:
    """Ajoute une note interne au dossier (chat : à la demande de l'utilisateur)."""
    response = client.post(f"/dossiers/{dossier_id}/notes", json={"content": content, "author": author})
    response.raise_for_status()
    return response.json()


def list_dossier_notes(client: httpx.Client, dossier_id: str) -> list[dict]:
    """Notes internes (non archivées) du dossier, la plus récente d'abord :
    contexte du chat. Tolérant : sans notes, le chat répond comme avant."""
    try:
        response = client.get(f"/dossiers/{dossier_id}/notes")
        response.raise_for_status()
        return response.json()
    except Exception:
        logger.warning("Could not load the notes of dossier %s", dossier_id, exc_info=True)
        return []


def finish_note_analysis(
    client: httpx.Client, note_id: str, *, status: str, proposal_count: int | None = None, error: str | None = None
) -> None:
    """Signale la fin de l'analyse d'une note (terminée ou en échec)."""
    body: dict = {"status": status}
    if proposal_count is not None:
        body["proposal_count"] = proposal_count
    if error is not None:
        body["error"] = error[:2000]
    client.post(f"/notes/{note_id}/analysis", json=body).raise_for_status()


# --- Brouillons de document : génération des valeurs de champs (issue #141) ---


def get_draft_context(client: httpx.Client, draft_id: str) -> dict:
    """Champs, éléments de la révision figée, notes, métadonnées et prompt en vigueur d'un brouillon."""
    response = client.get(f"/document-drafts/{draft_id}/context")
    response.raise_for_status()
    return response.json()


def propose_draft_field(client: httpx.Client, draft_id: str, name: str, body: dict) -> str:
    """Dépose la proposition de l'agent pour un champ. Renvoie « ok », « validated » (valeur validée : jamais
    réécrite) ou « invalid » (valeur refusée : ne correspond pas au type) ; toute autre erreur est levée."""
    response = client.post(f"/document-drafts/{draft_id}/fields/{name}/propose", json=body)
    if response.status_code == 409:
        return "validated"
    if response.status_code == 422:
        return "invalid"
    response.raise_for_status()
    return "ok"


def finish_draft_generation(
    client: httpx.Client,
    draft_id: str,
    *,
    status: str,
    proposal_count: int | None = None,
    missing: list[str] | None = None,
    truncated: bool = False,
    prompt_version: str | None = None,
    error: str | None = None,
) -> None:
    """Signale la fin de la génération (terminée ou en échec) sur le brouillon."""
    body: dict = {"status": status, "missing": missing or [], "truncated": truncated}
    if proposal_count is not None:
        body["proposal_count"] = proposal_count
    if prompt_version is not None:
        body["prompt_version"] = prompt_version
    if error is not None:
        body["error"] = error[:2000]
    client.post(f"/document-drafts/{draft_id}/generation", json=body).raise_for_status()


# --- Conversations & chat events ---


def get_conversation(client: httpx.Client, conversation_id: str) -> dict:
    """Récupère la conversation complète (historique des messages + modèle
    LLM préféré) pour construire le contexte du graphe LangGraph de chat."""
    response = client.get(f"/conversations/{conversation_id}")
    response.raise_for_status()
    return response.json()


def add_chat_event(
    client: httpx.Client,
    conversation_id: str,
    *,
    kind: str,
    data: dict,
) -> dict:
    """Dépose un événement de chat (tool_call, tool_result, thinking, done,
    error). Le frontend consomme ces événements via SSE pour streamer la
    progression de l'exécution en temps réel."""
    response = client.post(
        f"/conversations/{conversation_id}/chat-events",
        json={"kind": kind, "data": data},
    )
    response.raise_for_status()
    return response.json()


def deposit_assistant_message(
    client: httpx.Client,
    conversation_id: str,
    *,
    content: str,
    sources: list[dict] | None = None,
    tool_calls: list[dict] | None = None,
    external_sources: list[dict] | None = None,
) -> dict:
    """Dépose le message assistant final (avec sources) via l'API interne.
    Les sources référencent les documents/pages utilisés par l'agent pour
    construire sa réponse. `tool_calls` : les appels d'outils du dernier tour, dont ceux qui attendent l'accord
    de la personne."""
    response = client.post(
        f"/conversations/{conversation_id}/messages",
        json={
            "content": content,
            "sources": sources or [],
            "tool_calls": tool_calls or [],
            "external_sources": external_sources or [],
        },
    )
    response.raise_for_status()
    return response.json()


def record_chat_tool_result(client: httpx.Client, call_id: str, result: str) -> None:
    """Dépose le résultat d'un appel autorisé par la personne : il passe de « autorisé » à « exécuté »."""
    client.post(f"/chat-tool-calls/{call_id}/result", json={"result": result}).raise_for_status()


# --- Agent helper : conversation + chat events (issue #50) ---


def get_agent_conversation(client: httpx.Client, conversation_id: str) -> dict:
    """Historique user/assistant d'une conversation avec l'agent helper (pas de dossier associé -
    voir docs/mcp-helper-agent-plan.md)."""
    response = client.get(f"/agent-conversations/{conversation_id}")
    response.raise_for_status()
    return response.json()


def add_agent_chat_event(client: httpx.Client, conversation_id: str, *, kind: str, data: dict) -> dict:
    response = client.post(
        f"/agent-conversations/{conversation_id}/chat-events",
        json={"kind": kind, "data": data},
    )
    response.raise_for_status()
    return response.json()


def deposit_agent_assistant_message(
    client: httpx.Client,
    conversation_id: str,
    *,
    content: str,
    sources: list[dict] | None = None,
) -> dict:
    response = client.post(
        f"/agent-conversations/{conversation_id}/messages",
        json={"content": content, "sources": sources or []},
    )
    response.raise_for_status()
    return response.json()


# --- Agent helper : tools (analyses, dossiers) ---


def list_agent_analyses(client: httpx.Client, *, page: int = 1, page_size: int = 20, q: str | None = None) -> dict:
    params: dict[str, str | int] = {"page": page, "page_size": page_size}
    if q:
        params["q"] = q
    response = client.get("/agent/analyses", params=params)
    response.raise_for_status()
    return response.json()


def get_agent_analysis(client: httpx.Client, analyse_id: str) -> dict:
    response = client.get(f"/agent/analyses/{analyse_id}")
    response.raise_for_status()
    return response.json()


def create_agent_analysis(client: httpx.Client, *, name: str, description: str) -> dict:
    response = client.post("/agent/analyses", json={"name": name, "description": description})
    response.raise_for_status()
    return response.json()


def list_agent_dossiers(client: httpx.Client, *, page: int = 1, page_size: int = 20) -> dict:
    response = client.get("/agent/dossiers", params={"page": page, "page_size": page_size})
    response.raise_for_status()
    return response.json()


def get_agent_dossier(client: httpx.Client, dossier_id: str) -> dict:
    response = client.get(f"/agent/dossiers/{dossier_id}")
    response.raise_for_status()
    return response.json()


def create_agent_dossier(client: httpx.Client, *, name: str, analyse_id: str) -> dict:
    response = client.post("/agent/dossiers", json={"name": name, "analyse_id": analyse_id})
    response.raise_for_status()
    return response.json()


def launch_agent_dossier(client: httpx.Client, dossier_id: str) -> dict:
    response = client.post(f"/agent/dossiers/{dossier_id}/launch")
    response.raise_for_status()
    return response.json()


# --- Summaries (issue #52) ---


def set_document_summary_status(
    client: httpx.Client, document_id: str, *, status: str, error: str | None = None
) -> dict:
    response = client.put(
        f"/documents/{document_id}/summary-status",
        json={"status": status, "error": error},
    )
    response.raise_for_status()
    return response.json()


def deposit_document_summary(client: httpx.Client, document_id: str, *, content: str, model: str | None = None) -> dict:
    response = client.post(
        f"/documents/{document_id}/summaries",
        json={"content": content, "model": model},
    )
    response.raise_for_status()
    return response.json()


def set_dossier_summary_status(client: httpx.Client, dossier_id: str, *, status: str, error: str | None = None) -> dict:
    response = client.put(
        f"/dossiers/{dossier_id}/summary-status",
        json={"status": status, "error": error},
    )
    response.raise_for_status()
    return response.json()


def deposit_dossier_summary(client: httpx.Client, dossier_id: str, *, content: str, model: str | None = None) -> dict:
    response = client.post(
        f"/dossiers/{dossier_id}/summaries",
        json={"content": content, "model": model},
    )
    response.raise_for_status()
    return response.json()


# --- Analyse suggestions (issue #54 : dossier « à ranger ») ---


def set_suggestion_status(client: httpx.Client, dossier_id: str, *, status: str, error: str | None = None) -> dict:
    response = client.put(
        f"/dossiers/{dossier_id}/suggestion-status",
        json={"status": status, "error": error},
    )
    response.raise_for_status()
    return response.json()


def deposit_suggested_analyses(client: httpx.Client, dossier_id: str, *, suggestions: list[dict]) -> dict:
    response = client.post(
        f"/dossiers/{dossier_id}/suggestions",
        json={"suggestions": suggestions},
    )
    response.raise_for_status()
    return response.json()


# --- Outils MCP : définitions et appels (aucun jeton ne passe par le worker) ---


def _as_person(acting_user: str | None) -> dict[str, str]:
    """En-tête de la personne pour qui l'agent travaille, posé **par requête** : le client reste partagé."""
    return {"X-Acting-User": acting_user} if acting_user else {}


def resolve_tools(client: httpx.Client, tool_ids: list[str], acting_user: str | None) -> dict:
    """Les définitions des tools MCP que cette personne peut utiliser, et la liste de ceux qu'elle ne peut pas."""
    response = client.post("/tools/resolve", json={"tool_ids": tool_ids}, headers=_as_person(acting_user))
    response.raise_for_status()
    return response.json()


def call_tool(
    client: httpx.Client, tool_id: str, arguments: dict, *, acting_user: str | None, run_id: str | None
) -> dict:
    """Appelle un tool MCP par le backend, au nom de la personne. La réponse porte toujours `ok`, `code` et `output` :
    une erreur métier (session expirée, délai dépassé…) n'est pas une erreur HTTP."""
    response = client.post(
        f"/tools/{tool_id}/call", json={"arguments": arguments, "run_id": run_id}, headers=_as_person(acting_user)
    )
    response.raise_for_status()
    return response.json()


def search_knowledge(
    client: httpx.Client,
    analyse_id: str,
    query: str,
    top_k: int,
    *,
    acting_user: str | None,
    run_id: str | None,
) -> dict:
    """Cherche dans les collections que l'analyse autorise, par le backend, au nom de la personne. La réponse porte
    toujours `ok` et `code` : une erreur métier (session expirée, quota…) n'est pas une erreur HTTP."""
    response = client.post(
        "/knowledge/search",
        json={"analyse_id": analyse_id, "query": query, "top_k": top_k, "run_id": run_id},
        headers=_as_person(acting_user),
    )
    response.raise_for_status()
    return response.json()


# --- Index de recherche des dossiers ---


def get_search_config(client: httpx.Client, dossier_id: str) -> dict:
    """Réglages à appliquer au dossier, index actif et reconstruction en cours."""
    response = client.get(f"/dossiers/{dossier_id}/search-config")
    response.raise_for_status()
    return response.json()


def report_search_index(client: httpx.Client, dossier_id: str, **body) -> None:
    """Dit au backend où en est l'indexation du dossier (`status`, `chunk_count`, `error`, et à la création ou à la
    bascule `fingerprint`, `settings`, `replace_settings`)."""
    response = client.put(f"/dossiers/{dossier_id}/search-index", json=body)
    response.raise_for_status()


def get_index_rebuild(client: httpx.Client, rebuild_id: str) -> dict:
    response = client.get(f"/index-rebuilds/{rebuild_id}")
    response.raise_for_status()
    return response.json()


def report_index_rebuild(client: httpx.Client, rebuild_id: str, **body) -> dict:
    response = client.put(f"/index-rebuilds/{rebuild_id}", json=body)
    response.raise_for_status()
    return response.json()
