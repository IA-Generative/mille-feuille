"""Outils disponibles pour l'agent LangGraph.

Chaque outil est une fonction qui prend des paramètres simples et renvoie
une chaîne de texte (ou un dict sérialisable) que le LLM peut interpréter.
Les outils accèdent aux données du dossier via l'index BM25 et les
prédictions déjà déposées (classification + extraction).

Outils :
- search_documents : recherche BM25 dans le contenu des pages
- read_page : contenu complet d'une page spécifique
- view_classifications : toutes les classifications de pages (labels)
- view_entities : toutes les entités extraites

Suivi des sources : chaque appel d'outil qui consulte un document ou une
page enregistre une "source consultée" (page_id, document_id, excerpt).
Le graphe de chat récupère ces sources pour les déposer sur le message
assistant final via MessageSource.
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.bm25 import BM25Index, build_index_from_dossier

if TYPE_CHECKING:
    from app.analysis_tools import AnalysisProposer
    from app.note_tools import NoteWriter

logger = logging.getLogger(__name__)


@dataclass
class ConsultedSource:
    """Source consultée par l'agent pendant l'exécution. Mappée vers
    MessageSource lors du dépôt du message assistant final."""

    dossier_document_id: str | None = None
    page_ids: list[str] = field(default_factory=list)
    excerpt: str | None = None


class AgentTools:
    """Conteneur d'outils pour l'agent LangGraph. Construit à partir du
    dossier complet (avec pages et prédictions) récupéré via l'API interne.

    Le suivi des sources (_consulted_sources) accumule les pages/documents
    consultés pendant l'exécution. Le graphe de chat les récupère via
    consulted_sources() pour les déposer sur le message assistant final."""

    def __init__(
        self, dossier: dict, analysis: "AnalysisProposer | None" = None, notes: "NoteWriter | None" = None
    ) -> None:
        self._dossier = dossier
        # Propositions de modification de l'analyse (chat du dossier seulement).
        self._analysis = analysis
        # Ajout de notes internes (chat du dossier seulement).
        self._notes = notes
        self._index: BM25Index = build_index_from_dossier(dossier)
        self._pages_by_id: dict[str, dict] = {}
        self._pages_by_number: dict[int, dict] = {}
        self._documents_by_id: dict[str, dict] = {}
        for document in dossier.get("documents", []):
            self._documents_by_id[document["id"]] = document
            for page in document.get("pages", []):
                page["_document_name"] = document.get("name", "")
                page["_document_id"] = document.get("id")
                self._pages_by_id[page["id"]] = page
                self._pages_by_number[page["page_number"]] = page
        self._consulted_sources: list[ConsultedSource] = []
        self._assistant_question: str | None = None

    # --- Analyse de dossier : propositions (#115) ---

    @property
    def has_analysis(self) -> bool:
        """Le chat peut-il proposer de modifier l'analyse de ce dossier ?"""
        return self._analysis is not None and self._analysis.available

    # --- Notes internes ---

    @property
    def can_add_notes(self) -> bool:
        return self._notes is not None

    def add_note(self, content: str) -> str:
        return self._notes.add(content) if self._notes else "Les notes sont indisponibles."

    def view_analysis(self) -> str:
        return self._analysis.list_elements() if self._analysis else "Analyse indisponible."

    def propose_update(
        self,
        value: str,
        reason: str,
        element_id: str | None = None,
        kind: str | None = None,
        name: str | None = None,
    ) -> str:
        if self._analysis is None:
            return "Analyse indisponible."
        return self._analysis.propose(value=value, reason=reason, element_id=element_id, kind=kind, name=name)

    def analysis_proposals(self) -> tuple[str, list[str]] | None:
        """(identifiant de l'analyse, identifiants des propositions déposées
        pendant cette réponse), ou None s'il n'y en a pas."""
        if self._analysis is None or not self._analysis.proposal_ids or not self._analysis.analysis_id:
            return None
        return self._analysis.analysis_id, list(self._analysis.proposal_ids)

    # --- Passage de relais vers l'assistant de l'application ---

    def suggest_assistant(self, question: str) -> str:
        """Mémorise qu'on propose à l'utilisateur d'ouvrir l'assistant de
        l'application avec cette question. Sans effet de bord : seul le
        frontend ouvre l'assistant, après clic de l'utilisateur."""
        self._assistant_question = question.strip() or None
        return (
            "Une proposition d'ouvrir l'assistant de l'application sera affichée "
            "sous ta réponse. Explique brièvement que cette demande relève de "
            "l'assistant, sans tenter d'y répondre toi-même."
        )

    def assistant_question(self) -> str | None:
        """Question à pré-remplir dans l'assistant, si le LLM l'a proposé."""
        return self._assistant_question

    # --- Suivi des sources ---

    def consulted_sources(self) -> list[ConsultedSource]:
        """Renvoie la liste des sources consultées pendant l'exécution.
        Dédupliquée par (document_id, page_ids) pour éviter les doublons."""
        seen: set[str] = set()
        result: list[ConsultedSource] = []
        for src in self._consulted_sources:
            key = f"{src.dossier_document_id}:{'|'.join(sorted(src.page_ids))}"
            if key not in seen:
                seen.add(key)
                result.append(src)
        return result

    def _record_source(self, *, page_id: str | None = None, excerpt: str | None = None) -> None:
        """Enregistre une source consultée (page d'un document)."""
        if page_id is None:
            return
        page = self._pages_by_id.get(page_id)
        if page is None:
            return
        self._consulted_sources.append(
            ConsultedSource(
                dossier_document_id=page.get("_document_id"),
                page_ids=[page_id],
                excerpt=excerpt,
            )
        )

    # --- Outils exposés au LLM ---

    def search_documents(self, query: str) -> str:
        """Recherche dans le contenu des pages du dossier. Renvoie les
        pages les plus pertinentes avec un extrait du texte."""
        results = self._index.search(query)
        if not results:
            return "Aucun résultat trouvé pour cette recherche."
        lines = [f"{len(results)} résultat(s) trouvé(s) :\n"]
        for r in results:
            lines.append(f"📄 Page {r.page_number} ({r.document_name}) [score: {r.score:.2f}]\n   {r.excerpt}\n")
            # Enregistre chaque page trouvée comme source consultée.
            self._record_source(page_id=r.page_id, excerpt=r.excerpt)
        return "\n".join(lines)

    def read_page(self, page_number: int) -> str:
        """Lit le contenu complet d'une page spécifique par son numéro."""
        page = self._pages_by_number.get(page_number)
        if page is None:
            return f"Page {page_number} introuvable."
        doc_name = page.get("_document_name", "")
        content = page.get("content") or "(page vide)"
        # Enregistre la page lue comme source consultée, avec un extrait
        # (les 200 premiers caractères) pour le contexte.
        excerpt = (content[:200] + "...") if len(content) > 200 else content
        self._record_source(page_id=page["id"], excerpt=excerpt)
        return f"📄 Page {page_number} ({doc_name})\n\n{content}"

    def view_classifications(self) -> str:
        """Liste toutes les classifications de pages (labels prédits)."""
        entries: list[str] = []
        for page in self._pages_by_id.values():
            for pred in page.get("predictions", []):
                if pred.get("kind") == "label":
                    entries.append(
                        f"  Page {page['page_number']}: {pred['name']} (confiance: {pred.get('confidence', '?')})"
                    )
        if not entries:
            return "Aucune classification disponible."
        return "Classifications des pages :\n" + "\n".join(entries)

    def view_entities(self) -> str:
        """Liste toutes les entités extraites des pages."""
        seen: dict[str, dict] = {}
        for page in self._pages_by_id.values():
            for pred in page.get("predictions", []):
                if pred.get("kind") == "entity":
                    key = pred["name"]
                    if key not in seen:
                        seen[key] = {
                            "name": pred["name"],
                            "value": pred["value"],
                            "confidence": pred.get("confidence"),
                            "pages": [page["page_number"]],
                        }
                    else:
                        if page["page_number"] not in seen[key]["pages"]:
                            seen[key]["pages"].append(page["page_number"])
        if not seen:
            return "Aucune entité extraite."
        lines = ["Entités extraites :"]
        for entity in seen.values():
            pages_str = ", ".join(str(p) for p in entity["pages"])
            lines.append(
                f"  {entity['name']}: {entity['value']} "
                f"(confiance: {entity.get('confidence', '?')}, pages: {pages_str})"
            )
        return "\n".join(lines)

    # --- Métadonnées pour le LLM ---

    def tool_definitions(self) -> list[dict[str, Any]]:
        """Renvoie les définitions d'outils au format attendu par l'API
        OpenAI (function calling)."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_documents",
                    "description": (
                        "Recherche dans le contenu des pages du dossier. "
                        "Utilise cette recherche pour trouver des informations "
                        "pertinentes (noms, dates, adresses, montants...)."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Requête de recherche",
                            }
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_page",
                    "description": (
                        "Lit le contenu complet d'une page par son numéro. "
                        "Utilise cet outil après une recherche pour lire le "
                        "détail d'une page pertinente."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_number": {
                                "type": "integer",
                                "description": "Numéro de la page à lire",
                            }
                        },
                        "required": ["page_number"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "view_classifications",
                    "description": (
                        "Liste toutes les classifications de pages (types de "
                        "documents identifiés). Utilise cet outil pour voir "
                        "quels documents sont dans le dossier."
                    ),
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "view_entities",
                    "description": (
                        "Liste toutes les entités extraites (noms, dates, "
                        "adresses, montants...). Utilise cet outil pour voir "
                        "les informations déjà extraites du dossier."
                    ),
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "suggest_assistant",
                    "description": (
                        "À utiliser quand la demande de l'utilisateur concerne l'application "
                        "elle-même et non le contenu du dossier : créer ou configurer une "
                        "analyse, créer ou lancer un dossier, retrouver des analyses, "
                        "comprendre le fonctionnement de la plateforme. Propose à "
                        "l'utilisateur d'ouvrir l'assistant de l'application."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": (
                                    "La demande de l'utilisateur, reformulée pour l'assistant "
                                    "(elle sera pré-remplie dans sa zone de saisie)"
                                ),
                            }
                        },
                        "required": ["question"],
                    },
                },
            },
        ] + [*self._note_tool_definitions(), *self._analysis_tool_definitions()]

    def _note_tool_definitions(self) -> list[dict[str, Any]]:
        """Outil d'ajout de note interne : seulement quand le chat est branché sur les notes du dossier."""
        if not self.can_add_notes:
            return []
        return [
            {
                "type": "function",
                "function": {
                    "name": "add_note",
                    "description": (
                        "Ajoute une note interne au dossier, à la demande EXPLICITE de l'utilisateur (« ajoute une "
                        "note », « note que… », « garde en note… »). La note est enregistrée tout de suite, jamais "
                        "visible de l'usager. N'appelle pas cet outil de ta propre initiative, ni pour une simple "
                        "question. Une seule note par demande."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "Le texte de la note, fidèle à ce que l'utilisateur a demandé de noter",
                            }
                        },
                        "required": ["content"],
                    },
                },
            }
        ]

    def _analysis_tool_definitions(self) -> list[dict[str, Any]]:
        """Outils de proposition de modification de l'analyse : seulement quand
        le chat est branché sur l'analyse du dossier et que celle-ci existe."""
        if not self.has_analysis:
            return []
        return [
            {
                "type": "function",
                "function": {
                    "name": "view_analysis",
                    "description": (
                        "Liste les éléments de l'analyse du dossier (classifications, entités, synthèses...) "
                        "avec leur identifiant et leur valeur retenue. À appeler avant propose_update pour "
                        "connaître les identifiants."
                    ),
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "propose_update",
                    "description": (
                        "Propose de modifier l'analyse du dossier quand l'utilisateur apporte une information "
                        "claire (une correction, une vérification, une valeur manquante). N'APPLIQUE RIEN : "
                        "l'utilisateur accepte, modifie ou rejette la proposition. Une seule proposition par "
                        "information exprimée ; n'en fais pas pour une simple question. Pour modifier un "
                        "élément existant, donne element_id ; pour en ajouter un, donne kind (classification, "
                        "entity, synthesis ou field) et name."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "string", "description": "La nouvelle valeur proposée"},
                            "reason": {
                                "type": "string",
                                "description": "Pourquoi : l'information donnée par l'utilisateur, en une phrase",
                            },
                            "element_id": {
                                "type": "string",
                                "description": "Identifiant de l'élément à modifier (voir view_analysis)",
                            },
                            "kind": {
                                "type": "string",
                                "enum": ["classification", "entity", "synthesis", "field"],
                                "description": "Type de l'élément à ajouter (sans element_id)",
                            },
                            "name": {"type": "string", "description": "Nom de l'élément à ajouter (ex : adresse)"},
                        },
                        "required": ["value", "reason"],
                    },
                },
            },
        ]

    def dispatch_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Exécute un outil par son nom et renvoie le résultat."""
        if name == "search_documents":
            return self.search_documents(arguments.get("query", ""))
        if name == "read_page":
            return self.read_page(arguments.get("page_number", 0))
        if name == "view_classifications":
            return self.view_classifications()
        if name == "view_entities":
            return self.view_entities()
        if name == "suggest_assistant":
            return self.suggest_assistant(arguments.get("question", ""))
        if name == "add_note":
            return self.add_note(arguments.get("content", ""))
        if name == "view_analysis":
            return self.view_analysis()
        if name == "propose_update":
            return self.propose_update(
                arguments.get("value", ""),
                arguments.get("reason", ""),
                element_id=arguments.get("element_id"),
                kind=arguments.get("kind"),
                name=arguments.get("name"),
            )
        return f"Outil '{name}' inconnu."
