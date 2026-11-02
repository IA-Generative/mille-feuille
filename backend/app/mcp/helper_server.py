import uuid
from typing import Any

from fastapi import HTTPException
from mcp.server.mcpserver import MCPServer

from app.core.dossier_guard import check_dossier_access
from app.core.security.acting_user import context_for_user
from app.core.security.factory import RequestContext
from app.db import async_session_factory
from app.mcp.auth import get_current_identity
from app.models.agent_conversation import AgentConversation, AgentMessageRole
from app.repositories.agent_conversation_repository import AgentConversationRepository
from app.repositories.app_token_repository import AppTokenRepository
from app.repositories.dossier_repository import DossierRepository
from app.routers.analyses import create_analyse as _create_analyse
from app.routers.analyses import get_analyse as _get_analyse
from app.routers.analyses import list_analyses as _list_analyses
from app.routers.dossiers import _creation_access
from app.routers.dossiers import _get_or_404 as _get_dossier_or_404
from app.routers.dossiers import create_dossier_for as _create_dossier
from app.routers.dossiers import launch_dossier_for as _launch_dossier
from app.schemas.analyse import AnalyseCreate
from app.schemas.dossier import DossierCreate, DossierOut
from app.schemas.pagination import Page
from app.services.agent_dossier_files import AgentDossierFileIn, AgentDossierFilesIn
from app.services.agent_dossier_files import add_agent_dossier_files as _add_dossier_files

# Ce serveur MCP tourne dans le process du backend (mêmes repositories/DB
# que /api/analyses, /api/dossiers et /api/agent-conversations, pas
# d'appel HTTP interne) - il réutilise directement les fonctions des
# routers REST classiques, même pattern que app/mcp/server.py (éphémère).
# Voir docs/mcp-helper-agent-plan.md pour le design complet et
# mcp/README.md pour la doc client.
mcp_server = MCPServer(
    name="mille-feuille-helper",
    instructions=(
        "Recherche/création d'analyses et de dossiers persistants, ajout de fichiers, lancement du "
        "pipeline (classification, extraction, agents) en asynchrone, consultation des résultats. "
        "Cycle typique : search_analyses ou create_analysis -> create_dossier -> add_dossier_files -> "
        "run_dossier -> get_dossier_results en boucle jusqu'à statut terminal. Contrairement au serveur "
        "éphémère (/mcp), ces ressources sont persistantes (pas de TTL) et partagées sur la plateforme. "
        "Passez conversation_id (obtenu via create_agent_conversation) pour journaliser vos appels - "
        "optionnel, un client qui gère son propre contexte peut l'omettre."
    ),
)


def _http_error_to_dict(error: HTTPException) -> dict[str, Any]:
    return {"error": error.detail, "status_code": error.status_code}


def _dossier_out(dossier: Any) -> dict[str, Any]:
    # create_dossier/get_dossier/launch_dossier (app/routers/dossiers.py)
    # renvoient l'objet ORM Dossier tel quel (la conversion vers DossierOut
    # est normalement faite par FastAPI via response_model, qui ne
    # s'applique pas quand on appelle la fonction directement) - donc
    # conversion manuelle ici plutôt que côté MCP client.
    return DossierOut.model_validate(dossier).model_dump(mode="json")


async def _call_traced(
    db,
    identity,
    conversation_id: str | None,
    tool_name: str,
    arguments: dict[str, Any],
    fn,
) -> dict[str, Any]:
    """Exécute un tool et, si conversation_id est fourni, journalise
    l'appel (tool_call) et son résultat (tool_result/error) dans
    agent_messages - scopé à l'appelant (identity.id), comme les
    ressources éphémères. Centralise aussi la conversion des HTTPException
    levées par les fonctions de router en {"error", "status_code"}."""
    repository = AgentConversationRepository(db)
    conversation: AgentConversation | None = None
    if conversation_id:
        try:
            conversation_uuid = uuid.UUID(conversation_id)
        except ValueError:
            return {"error": "conversation_id invalide", "status_code": 400}
        conversation = await repository.get(conversation_uuid)
        if conversation is None or conversation.created_by != identity.id:
            return {"error": "Conversation introuvable", "status_code": 404}
        await repository.add_message(
            conversation, AgentMessageRole.TOOL_CALL, tool_name=tool_name, data={"arguments": arguments}
        )

    try:
        result = await fn()
    except HTTPException as error:
        result = _http_error_to_dict(error)

    if conversation is not None:
        is_error = isinstance(result, dict) and "error" in result
        role = AgentMessageRole.ERROR if is_error else AgentMessageRole.TOOL_RESULT
        await repository.add_message(conversation, role, tool_name=tool_name, data={"result": result})
    return result


async def _acting(db, identity) -> RequestContext:
    """Les droits de la personne qui a créé le jeton d'application (issue #222) : l'agent ne voit jamais plus de
    dossiers qu'elle. Un jeton dont le propriétaire est inconnu de l'annuaire n'a aucun groupe."""
    app_token = await AppTokenRepository(db).get(uuid.UUID(identity.id))
    return await context_for_user(db, app_token.created_by if app_token else None)


@mcp_server.tool()
async def create_agent_conversation(title: str | None = None) -> dict[str, Any]:
    """Crée une conversation pour journaliser vos appels de tools (facultatif - voir le paramètre
    conversation_id de chaque tool). Renvoie {"conversation_id": "<uuid>"}."""
    identity = get_current_identity()
    async with async_session_factory() as db:
        conversation = await AgentConversationRepository(db).create(created_by=identity.id, title=title)
    return {"conversation_id": str(conversation.id)}


@mcp_server.tool()
async def list_analyses(page: int = 1, page_size: int = 20, conversation_id: str | None = None) -> dict[str, Any]:
    """Liste paginée des analyses persistantes de la plateforme (classification, extraction, agents)."""
    identity = get_current_identity()
    arguments = {"page": page, "page_size": page_size}
    async with async_session_factory() as db:

        async def run():
            result = await _list_analyses(db, page=page, page_size=page_size, q=None)
            return result.model_dump(mode="json")

        return await _call_traced(db, identity, conversation_id, "list_analyses", arguments, run)


@mcp_server.tool()
async def search_analyses(
    q: str, page: int = 1, page_size: int = 20, conversation_id: str | None = None
) -> dict[str, Any]:
    """Recherche des analyses persistantes par nom (insensible à la casse)."""
    identity = get_current_identity()
    arguments = {"q": q, "page": page, "page_size": page_size}
    async with async_session_factory() as db:

        async def run():
            result = await _list_analyses(db, page=page, page_size=page_size, q=q)
            return result.model_dump(mode="json")

        return await _call_traced(db, identity, conversation_id, "search_analyses", arguments, run)


@mcp_server.tool()
async def get_analysis(analyse_id: str, conversation_id: str | None = None) -> dict[str, Any]:
    """Détail complet d'une analyse persistante (labels, entités, agents, prompts)."""
    identity = get_current_identity()
    arguments = {"analyse_id": analyse_id}
    async with async_session_factory() as db:

        async def run():
            result = await _get_analyse(uuid.UUID(analyse_id), db)
            return result.model_dump(mode="json")

        return await _call_traced(db, identity, conversation_id, "get_analysis", arguments, run)


@mcp_server.tool()
async def create_analysis(name: str, description: str, conversation_id: str | None = None) -> dict[str, Any]:
    """Crée une analyse persistante (nom + description). La classification, l'extraction et les
    agents se configurent ensuite via la plateforme (pas de tool dédié pour l'instant).

    Renvoie l'analyse créée - à réutiliser avec create_dossier."""
    identity = get_current_identity()
    arguments = {"name": name, "description": description}
    async with async_session_factory() as db:

        async def run():
            result = await _create_analyse(AnalyseCreate(name=name, description=description), db)
            return result.model_dump(mode="json")

        return await _call_traced(db, identity, conversation_id, "create_analysis", arguments, run)


@mcp_server.tool()
async def create_dossier(name: str, analyse_id: str, conversation_id: str | None = None) -> dict[str, Any]:
    """Crée un dossier persistant, associé à une analyse existante. Renvoie le dossier créé (vide,
    sans document) - à réutiliser avec add_dossier_files."""
    identity = get_current_identity()
    arguments = {"name": name, "analyse_id": analyse_id}
    async with async_session_factory() as db:

        async def run():
            person = await _acting(db, identity)
            body = DossierCreate(name=name, analyse_id=uuid.UUID(analyse_id))
            visibility, group_paths = _creation_access(body, person)  # restreint aux groupes de la personne
            dossier = await _create_dossier(body, db, person, visibility, group_paths)
            return _dossier_out(dossier)

        return await _call_traced(db, identity, conversation_id, "create_dossier", arguments, run)


@mcp_server.tool()
async def add_dossier_files(
    dossier_id: str, files: list[dict[str, str]], conversation_id: str | None = None
) -> dict[str, Any]:
    """Ajoute des fichiers à un dossier existant.

    files : [{"name": str, "content_base64": str, "mimetype": str}] - contenu du fichier encodé en
    base64 (pas de multipart en MCP). Renvoie le dossier mis à jour avec ses documents."""
    identity = get_current_identity()
    arguments = {"dossier_id": dossier_id, "file_count": len(files)}
    async with async_session_factory() as db:

        async def run():
            body = AgentDossierFilesIn(files=[AgentDossierFileIn(**f) for f in files])
            dossier = await _add_dossier_files(uuid.UUID(dossier_id), body, db, await _acting(db, identity))
            return _dossier_out(dossier)

        return await _call_traced(db, identity, conversation_id, "add_dossier_files", arguments, run)


@mcp_server.tool()
async def list_dossiers(page: int = 1, page_size: int = 20, conversation_id: str | None = None) -> dict[str, Any]:
    """Liste paginée des dossiers persistants de la plateforme."""
    identity = get_current_identity()
    arguments = {"page": page, "page_size": page_size}
    async with async_session_factory() as db:

        async def run():
            person = await _acting(db, identity)
            dossiers, total = await DossierRepository(db).list_paginated(page=page, page_size=page_size, user=person)
            items = [DossierOut.model_validate(d) for d in dossiers]
            return Page.of(items, total=total, page=page, page_size=page_size).model_dump(mode="json")

        return await _call_traced(db, identity, conversation_id, "list_dossiers", arguments, run)


@mcp_server.tool()
async def get_dossier(dossier_id: str, conversation_id: str | None = None) -> dict[str, Any]:
    """Détail d'un dossier : documents, statut, étapes d'exécution, résultats (classifications,
    entités, sorties des agents une fois le pipeline terminé)."""
    identity = get_current_identity()
    arguments = {"dossier_id": dossier_id}
    async with async_session_factory() as db:

        async def run():
            person = await _acting(db, identity)
            await check_dossier_access(db, uuid.UUID(dossier_id), person)
            dossier = await _get_dossier_or_404(DossierRepository(db), uuid.UUID(dossier_id), person)
            return _dossier_out(dossier)

        return await _call_traced(db, identity, conversation_id, "get_dossier", arguments, run)


@mcp_server.tool()
async def run_dossier(dossier_id: str, conversation_id: str | None = None) -> dict[str, Any]:
    """Lance le pipeline (classification, extraction, agents) sur un dossier déjà créé, avec ses
    fichiers déjà ajoutés. Démarre en arrière-plan (Celery) et renvoie immédiatement - suivre la
    progression avec get_dossier_results en boucle jusqu'à un statut terminal."""
    identity = get_current_identity()
    arguments = {"dossier_id": dossier_id}
    async with async_session_factory() as db:

        async def run():
            person = await _acting(db, identity)
            await check_dossier_access(db, uuid.UUID(dossier_id), person, method="POST", write=True)
            dossier = await _launch_dossier(uuid.UUID(dossier_id), db, person)
            return _dossier_out(dossier)

        return await _call_traced(db, identity, conversation_id, "run_dossier", arguments, run)


@mcp_server.tool()
async def get_dossier_results(dossier_id: str, conversation_id: str | None = None) -> dict[str, Any]:
    """Résultats d'un dossier (statut, classifications, entités extraites, sorties des agents) -
    alias de get_dossier, à appeler en boucle après run_dossier jusqu'à statut terminal."""
    identity = get_current_identity()
    arguments = {"dossier_id": dossier_id}
    async with async_session_factory() as db:

        async def run():
            person = await _acting(db, identity)
            await check_dossier_access(db, uuid.UUID(dossier_id), person)
            dossier = await _get_dossier_or_404(DossierRepository(db), uuid.UUID(dossier_id), person)
            return _dossier_out(dossier)

        return await _call_traced(db, identity, conversation_id, "get_dossier_results", arguments, run)
