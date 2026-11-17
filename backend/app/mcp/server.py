import base64
import uuid
from typing import Any

from fastapi import HTTPException
from mcp.server.mcpserver import MCPServer

from app.db import async_session_factory
from app.mcp.auth import get_current_identity
from app.repositories.analyse_repository import AnalyseRepository
from app.routers.ephemeral import (
    _create_run,
    _validate_ttl_hours,
)
from app.routers.ephemeral import create_ephemeral_analyse as _create_analyse_endpoint
from app.routers.ephemeral import delete_ephemeral_analyse as _delete_analyse_endpoint
from app.routers.ephemeral import delete_ephemeral_run as _delete_run_endpoint
from app.routers.ephemeral import get_ephemeral_analyse as _get_analyse_endpoint
from app.routers.ephemeral import get_ephemeral_run as _get_run_endpoint
from app.routers.ephemeral import stop_ephemeral_run as _stop_run_endpoint
from app.schemas.analyse import AgentCreate, EntityDefinitionIn, LabelDefinitionIn
from app.schemas.ephemeral import EphemeralAnalyseCreate, EphemeralRunCreated

# Ce serveur MCP tourne dans le process du backend (mêmes repositories/DB
# que /api/ephemeral/*, pas d'appel HTTP interne) - il réutilise directement
# les fonctions des endpoints REST de app/routers/ephemeral.py : ce sont de
# simples fonctions async, les paramètres Depends()/Annotated ne sont que des
# métadonnées pour FastAPI, rien n'empêche de les appeler ici avec un `db`
# et une `identity` déjà résolus. Voir mcp/README.md pour la doc client,
# docs/ephemeral-api.md pour le design REST équivalent.
mcp_server = MCPServer(
    name="mille-feuille-ephemeral",
    instructions=(
        "Analyse à la demande de documents (classification, extraction d'entités, agents), temporaire "
        "par défaut (TTL). Cycle typique : create_ephemeral_analysis (ou un analyse_id déjà connu) -> "
        "run_ephemeral_analysis avec des fichiers -> get_ephemeral_run en boucle jusqu'à statut terminal "
        "-> exploiter le résultat -> delete_ephemeral_run si le résultat n'a plus besoin d'être conservé."
    ),
)


def _http_error_to_dict(error: HTTPException) -> dict[str, Any]:
    return {"error": error.detail, "status_code": error.status_code}


@mcp_server.tool()
async def create_ephemeral_analysis(
    name: str,
    description: str = "",
    persist: bool = False,
    classification_prompt: str = "",
    labels: list[dict[str, str]] | None = None,
    extraction_prompt: str = "",
    entities: list[dict[str, str]] | None = None,
    agents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Crée une analyse (classification, extraction, agents) en un seul appel.

    persist=false (défaut) : purgée automatiquement une fois son TTL écoulé (calculé à la fin du dernier
    run l'ayant utilisée, jamais à la création). persist=true : conservée indéfiniment.
    labels: [{"name": str, "definition": str}]. entities: [{"name": str, "definition": str,
    "type": "texte"|"date"|"nombre"|"booléen"|"identifiant",
    "nature": "entité" (GLiNER, défaut) | "sémantique" (LLM)}]. agents: [{"name": str, "prompt": str,
    "tools": [str], "output": bool, "model": str|null}].

    Renvoie {"analyse_id": "<uuid>"} - à réutiliser avec run_ephemeral_analysis.
    """
    identity = get_current_identity()
    body = EphemeralAnalyseCreate(
        name=name,
        description=description,
        persist=persist,
        classification_prompt=classification_prompt,
        labels=[LabelDefinitionIn(**lbl) for lbl in labels or []],
        extraction_prompt=extraction_prompt,
        entities=[EntityDefinitionIn(**ent) for ent in entities or []],
        agents=[AgentCreate(**agent) for agent in agents or []],
    )
    async with async_session_factory() as db:
        try:
            created = await _create_analyse_endpoint(body, db, identity)
        except HTTPException as error:
            return _http_error_to_dict(error)
    return created.model_dump(mode="json")


@mcp_server.tool()
async def get_ephemeral_analysis(analyse_id: str) -> dict[str, Any]:
    """Consulte la définition complète d'une analyse éphémère (classification, extraction, agents,
    persist, expires_at). Scope strict au créateur de l'analyse - erreur si elle n'existe pas, n'est pas
    éphémère, ou appartient à un autre jeton API."""
    identity = get_current_identity()
    async with async_session_factory() as db:
        try:
            out = await _get_analyse_endpoint(uuid.UUID(analyse_id), db, identity)
        except HTTPException as error:
            return _http_error_to_dict(error)
    return out.model_dump(mode="json")


@mcp_server.tool()
async def delete_ephemeral_analysis(analyse_id: str) -> dict[str, Any]:
    """Supprime une analyse éphémère immédiatement, sans attendre son TTL. Échoue si des runs
    (dossier_ephemere) la référencent encore - supprimez-les d'abord avec delete_ephemeral_run."""
    identity = get_current_identity()
    async with async_session_factory() as db:
        try:
            await _delete_analyse_endpoint(uuid.UUID(analyse_id), db, identity)
        except HTTPException as error:
            return _http_error_to_dict(error)
    return {"deleted": True}


@mcp_server.tool()
async def run_ephemeral_analysis(
    analyse_id: str,
    files: list[dict[str, str]],
    persist: bool = False,
    ttl_hours: int | None = None,
) -> dict[str, Any]:
    """Lance le pipeline complet (classification, extraction, agents) sur un ensemble de documents.
    Démarre immédiatement, pas d'étape séparée pour lancer le run.

    analyse_id : une analyse créée par create_ephemeral_analysis, ou l'id d'une analyse classique déjà
    existante sur la plateforme (elle n'est alors jamais modifiée).
    files : [{"name": str, "content_base64": str, "mimetype": str}] - contenu du fichier encodé en base64
    (pas de multipart en MCP).
    ttl_hours : défaut 24h, max 17520h (2 ans). persist=false (défaut) : purgé automatiquement à la fin de
    son TTL, calculé à la fin du run (jamais à la création).

    Renvoie {"run_id": "<uuid>"} - à suivre avec get_ephemeral_run.
    """
    identity = get_current_identity()
    async with async_session_factory() as db:
        analyse = await AnalyseRepository(db).get(uuid.UUID(analyse_id))
        if analyse is None:
            return {"error": "Analyse introuvable", "status_code": 404}
        try:
            ttl = _validate_ttl_hours(ttl_hours)
        except HTTPException as error:
            return _http_error_to_dict(error)
        decoded = [
            (f["name"], base64.b64decode(f["content_base64"]), f.get("mimetype", "application/octet-stream"))
            for f in files
        ]
        dossier = await _create_run(
            db=db, identity=identity, analyse=analyse, files=decoded, persist=persist, ttl_hours=ttl
        )
    return EphemeralRunCreated(run_id=dossier.id).model_dump(mode="json")


@mcp_server.tool()
async def get_ephemeral_run(run_id: str) -> dict[str, Any]:
    """Statut d'un run (en_attente/en_cours/terminé/arrêté/échec) et, une fois terminé, ses résultats
    (classification, entités, sorties des agents). Scope strict au créateur du run."""
    identity = get_current_identity()
    async with async_session_factory() as db:
        try:
            out = await _get_run_endpoint(uuid.UUID(run_id), db, identity)
        except HTTPException as error:
            return _http_error_to_dict(error)
    return out.model_dump(mode="json")


@mcp_server.tool()
async def stop_ephemeral_run(run_id: str) -> dict[str, Any]:
    """Arrête un run en cours (no-op s'il est déjà dans un état terminal). N'efface rien : le run reste
    consultable, et sera purgé au TTL ou supprimable via delete_ephemeral_run."""
    identity = get_current_identity()
    async with async_session_factory() as db:
        try:
            out = await _stop_run_endpoint(uuid.UUID(run_id), db, identity)
        except HTTPException as error:
            return _http_error_to_dict(error)
    return out.model_dump(mode="json")


@mcp_server.tool()
async def delete_ephemeral_run(run_id: str) -> dict[str, Any]:
    """Arrête (si besoin) puis supprime un run immédiatement - documents, étapes d'exécution, résultats et
    fichiers S3 compris. N'attend pas expires_at. Ne touche pas à l'analyse liée."""
    identity = get_current_identity()
    async with async_session_factory() as db:
        try:
            await _delete_run_endpoint(uuid.UUID(run_id), db, identity)
        except HTTPException as error:
            return _http_error_to_dict(error)
    return {"deleted": True}
