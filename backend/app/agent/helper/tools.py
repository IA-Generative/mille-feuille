"""Les outils de l'assistant de l'application (issue #50) : retrouver ou créer des analyses et des dossiers, lancer le
pipeline, en consulter les résultats. L'assistant n'est rattaché à aucun dossier au départ, il les découvre au fil de la
conversation.

Les outils appellent directement les fonctions des routeurs (comme le serveur MCP de l'assistant,
app/mcp/helper_server.py) au nom de la personne qui a ouvert la conversation : l'assistant ne voit jamais plus de
dossiers qu'elle (issue #222). Pas d'outil d'envoi de fichiers : un modèle ne peut pas produire le contenu binaire d'un
vrai document depuis un message texte ; les fichiers s'ajoutent par le bouton de la fenêtre de l'assistant.

Suivi des ressources consultées : chaque outil qui lit ou crée un dossier ou une analyse note une « ressource »
(dossier ou analyse, plus un court extrait) ; elles sont déposées avec la réponse, pour que l'interface lie
directement le dossier trouvé ou créé."""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.core.dossier_guard import check_dossier_access
from app.core.security.acting_user import context_for_user
from app.db import async_session_factory
from app.repositories.dossier_repository import DossierRepository
from app.routers.analyses import create_analyse, get_analyse, list_analyses
from app.routers.dossiers import _creation_access, create_dossier_for, launch_dossier_for
from app.routers.dossiers import _get_or_404 as get_dossier_or_404
from app.schemas.analyse import AnalyseCreate
from app.schemas.dossier import DossierCreate, DossierOut

logger = logging.getLogger(__name__)


@dataclass
class ConsultedResource:
    """Ressource consultée par l'agent pendant l'exécution, déposée avec le message final."""

    dossier_id: str | None = None
    analyse_id: str | None = None
    excerpt: str | None = None


def _error_message(error: HTTPException) -> str:
    return f"Erreur : {error.detail}"


def _tool_def(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required or []},
        },
    }


class HelperTools:
    def __init__(self, acting_user: str) -> None:
        self._acting_user = acting_user
        self._consulted: list[ConsultedResource] = []

    # --- Suivi des ressources ---

    def consulted_resources(self) -> list[ConsultedResource]:
        """Les ressources consultées pendant l'exécution, dédupliquées par (dossier, analyse)."""
        seen: set[tuple[str | None, str | None]] = set()
        result: list[ConsultedResource] = []
        for res in self._consulted:
            key = (res.dossier_id, res.analyse_id)
            if key not in seen:
                seen.add(key)
                result.append(res)
        return result

    def _record(
        self, *, dossier_id: str | None = None, analyse_id: str | None = None, excerpt: str | None = None
    ) -> None:
        self._consulted.append(ConsultedResource(dossier_id=dossier_id, analyse_id=analyse_id, excerpt=excerpt))

    # --- Analyses ---

    async def _analyses(self, *, page: int = 1, page_size: int = 20, q: str | None = None) -> str:
        async with async_session_factory() as db:
            result = await list_analyses(db, page=page, page_size=page_size, q=q)
        if not result.items:
            return "Aucune analyse trouvée."
        lines = [f"{result.total} analyse(s) :"]
        for a in result.items:
            lines.append(f"- {a.name} (id: {a.id}) - {a.agent_count} agent(s), {a.description}")
            self._record(analyse_id=str(a.id), excerpt=a.name)
        return "\n".join(lines)

    async def list_analyses(self, page: int = 1, page_size: int = 20) -> str:
        """Liste les analyses persistantes de la plateforme."""
        return await self._analyses(page=page, page_size=page_size)

    async def search_analyses(self, q: str) -> str:
        """Recherche des analyses persistantes par nom."""
        return await self._analyses(q=q)

    async def get_analysis(self, analyse_id: str) -> str:
        """Détail complet d'une analyse (labels, entités, prompts)."""
        try:
            async with async_session_factory() as db:
                analyse = await get_analyse(uuid.UUID(analyse_id), db)
        except ValueError:
            return "Erreur : identifiant d'analyse invalide."
        except HTTPException as error:
            return _error_message(error)
        labels = ", ".join(label.name for label in analyse.classification.labels) or "(aucun)"
        entities = ", ".join(entity.name for entity in analyse.extraction.entities) or "(aucune)"
        self._record(analyse_id=str(analyse.id), excerpt=analyse.name)
        return (
            f"Analyse « {analyse.name} » (id: {analyse.id})\n"
            f"Description : {analyse.description}\n"
            f"Labels de classification : {labels}\n"
            f"Entités d'extraction : {entities}"
        )

    async def create_analysis(self, name: str, description: str) -> str:
        """Crée une analyse persistante (nom + description) - la classification, l'extraction et les agents se
        configurent ensuite via la plateforme."""
        async with async_session_factory() as db:
            # Au nom de la personne qui a ouvert la conversation : c'est elle, avec les administrateurs, qui gérera
            # l'analyse.
            person = await context_for_user(db, self._acting_user)
            analyse = await create_analyse(AnalyseCreate(name=name, description=description), db, person)
        self._record(analyse_id=str(analyse.id), excerpt=analyse.name)
        return f"Analyse « {analyse.name} » créée (id: {analyse.id})."

    # --- Dossiers ---

    async def list_dossiers(self, page: int = 1, page_size: int = 20) -> str:
        """Liste les dossiers que la personne peut voir."""
        async with async_session_factory() as db:
            person = await context_for_user(db, self._acting_user)
            dossiers, total = await DossierRepository(db).list_paginated(page=page, page_size=page_size, user=person)
            items = [DossierOut.model_validate(d) for d in dossiers]
        if not items:
            return "Aucun dossier trouvé."
        lines = [f"{total} dossier(s) :"]
        for d in items:
            lines.append(f"- {d.name} (id: {d.id}) - statut : {d.status}")
            self._record(dossier_id=str(d.id), excerpt=d.name)
        return "\n".join(lines)

    async def get_dossier(self, dossier_id: str) -> str:
        """Détail d'un dossier : documents, statut, résultats une fois le pipeline terminé."""
        try:
            async with async_session_factory() as db:
                person = await context_for_user(db, self._acting_user)
                await check_dossier_access(db, uuid.UUID(dossier_id), person)
                dossier = DossierOut.model_validate(
                    await get_dossier_or_404(DossierRepository(db), uuid.UUID(dossier_id), person)
                )
        except ValueError:
            return "Erreur : identifiant de dossier invalide."
        except HTTPException as error:
            return _error_message(error)
        return self._format_dossier(dossier)

    async def create_dossier(self, name: str, analyse_id: str) -> str:
        """Crée un dossier persistant, associé à une analyse existante."""
        try:
            body = DossierCreate(name=name, analyse_id=uuid.UUID(analyse_id))
            async with async_session_factory() as db:
                person = await context_for_user(db, self._acting_user)
                visibility, group_paths = _creation_access(body, person)
                dossier = DossierOut.model_validate(await create_dossier_for(body, db, person, visibility, group_paths))
        except ValueError:
            return "Erreur : identifiant d'analyse invalide."
        except HTTPException as error:
            return _error_message(error)
        self._record(dossier_id=str(dossier.id), excerpt=dossier.name)
        return f"Dossier « {dossier.name} » créé (id: {dossier.id}), sans document pour l'instant."

    async def run_dossier(self, dossier_id: str) -> str:
        """Lance le pipeline (classification, extraction, agents) sur un dossier déjà créé, avec ses fichiers déjà
        ajoutés. Démarre en arrière-plan, revient immédiatement."""
        try:
            async with async_session_factory() as db:
                person = await context_for_user(db, self._acting_user)
                await check_dossier_access(db, uuid.UUID(dossier_id), person, method="POST", write=True)
                dossier = DossierOut.model_validate(await launch_dossier_for(uuid.UUID(dossier_id), db, person))
        except ValueError:
            return "Erreur : identifiant de dossier invalide."
        except HTTPException as error:
            return _error_message(error)
        self._record(dossier_id=str(dossier.id), excerpt=dossier.name)
        return f"Pipeline lancé sur « {dossier.name} » (statut : {dossier.status})."

    async def get_dossier_results(self, dossier_id: str) -> str:
        """Résultats d'un dossier (statut, synthèses des agents) - à appeler en boucle après run_dossier jusqu'à un
        statut terminal."""
        return await self.get_dossier(dossier_id)

    def _format_dossier(self, dossier: DossierOut) -> str:
        self._record(dossier_id=str(dossier.id), excerpt=dossier.name)
        lines = [
            f"Dossier « {dossier.name} » (id: {dossier.id})",
            f"Statut : {dossier.status}",
            f"Documents : {len(dossier.documents)}",
        ]
        syntheses = [step for step in dossier.execution_steps if step.kind == "agent" and step.output]
        if syntheses:
            lines.append("\nSynthèses des agents :")
            lines.extend(f"\n[{step.label}]\n{step.output}" for step in syntheses)
        return "\n".join(lines)

    # --- Métadonnées pour le LLM ---

    def tool_definitions(self) -> list[dict[str, Any]]:
        """Les définitions d'outils au format de l'API OpenAI (function calling)."""
        dossier_id = {"dossier_id": {"type": "string", "description": "Identifiant du dossier"}}
        return [
            _tool_def(
                "list_analyses",
                "Liste les analyses persistantes de la plateforme (classification, extraction, agents).",
                {},
            ),
            _tool_def(
                "search_analyses",
                "Recherche des analyses persistantes par nom. Utilise cet outil avant d'en créer une "
                "nouvelle, pour proposer de réutiliser une analyse existante si pertinent.",
                {"q": {"type": "string", "description": "Terme de recherche"}},
                required=["q"],
            ),
            _tool_def(
                "get_analysis",
                "Détail complet d'une analyse (labels, entités, prompts).",
                {"analyse_id": {"type": "string", "description": "Identifiant de l'analyse"}},
                required=["analyse_id"],
            ),
            _tool_def(
                "create_analysis",
                "Crée une analyse persistante (nom + description).",
                {
                    "name": {"type": "string", "description": "Nom de l'analyse"},
                    "description": {"type": "string", "description": "Objectif métier de l'analyse"},
                },
                required=["name", "description"],
            ),
            _tool_def("list_dossiers", "Liste les dossiers persistants de la plateforme.", {}),
            _tool_def(
                "get_dossier",
                "Détail d'un dossier : documents, statut, résultats une fois le pipeline terminé.",
                dossier_id,
                required=["dossier_id"],
            ),
            _tool_def(
                "create_dossier",
                "Crée un dossier persistant, associé à une analyse existante.",
                {
                    "name": {"type": "string", "description": "Nom du dossier"},
                    "analyse_id": {"type": "string", "description": "Identifiant de l'analyse associée"},
                },
                required=["name", "analyse_id"],
            ),
            _tool_def(
                "run_dossier",
                "Lance le pipeline (classification, extraction, agents) sur un dossier - démarre en "
                "arrière-plan, revient immédiatement.",
                dossier_id,
                required=["dossier_id"],
            ),
            _tool_def(
                "get_dossier_results",
                "Résultats d'un dossier (statut, synthèses des agents) - à appeler après run_dossier "
                "jusqu'à un statut terminal.",
                dossier_id,
                required=["dossier_id"],
            ),
        ]

    async def dispatch_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Exécute un outil par son nom et renvoie le résultat."""
        if name == "list_analyses":
            return await self.list_analyses()
        if name == "search_analyses":
            return await self.search_analyses(arguments.get("q", ""))
        if name == "get_analysis":
            return await self.get_analysis(arguments.get("analyse_id", ""))
        if name == "create_analysis":
            return await self.create_analysis(arguments.get("name", ""), arguments.get("description", ""))
        if name == "list_dossiers":
            return await self.list_dossiers()
        if name == "get_dossier":
            return await self.get_dossier(arguments.get("dossier_id", ""))
        if name == "create_dossier":
            return await self.create_dossier(arguments.get("name", ""), arguments.get("analyse_id", ""))
        if name == "run_dossier":
            return await self.run_dossier(arguments.get("dossier_id", ""))
        if name == "get_dossier_results":
            return await self.get_dossier_results(arguments.get("dossier_id", ""))
        return f"Outil '{name}' inconnu."
