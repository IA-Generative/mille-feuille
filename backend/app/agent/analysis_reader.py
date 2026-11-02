"""L'analyse d'un agent, en lecture seule : ce qu'elle définit (objectif, prompts, labels, entités, agents), ce que le
dossier en a tiré (éléments) et ce que les autres agents en ont conclu.

Le lecteur est construit pour un dossier : un agent ne peut lire que l'analyse de ce dossier et ses synthèses, jamais
celles d'un autre. Il n'écrit rien (les propositions de correction restent propres au chat du dossier)."""

import logging
import uuid
from typing import Any

from app.agent.analysis_tools import AnalysisProposer
from app.db import async_session_factory
from app.repositories.analyse_repository import AnalyseRepository
from app.services.internal_analyse import build_internal_analyse

logger = logging.getLogger(__name__)

# Une synthèse d'agent peut être longue : on en donne assez pour répondre, pas de quoi noyer le contexte.
OUTPUT_CHARS = 6000

READ_ANALYSIS = "read_analysis"
LIST_AGENTS = "list_agents"
READ_AGENT_OUTPUT = "read_agent_output"


def _function(name: str, description: str, properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties or {}, "required": required or []},
        },
    }


DEFINITIONS = [
    _function(
        READ_ANALYSIS,
        "Lit la définition de l'analyse de ce dossier : son objectif, ses consignes de classification et d'extraction, "
        "ses labels, ses entités et ses agents.",
    ),
    _function(LIST_AGENTS, "Liste les agents de l'analyse, avec leur rôle et leurs outils."),
    _function(
        READ_AGENT_OUTPUT,
        "Lit la synthèse qu'un autre agent de l'analyse a produite sur ce dossier.",
        {"agent": {"type": "string", "description": "Le nom de l'agent (voir list_agents)"}},
        ["agent"],
    ),
]


class AnalysisReader:
    """`load()` lit l'analyse une fois, avant que le modèle ne parle."""

    def __init__(self, *, dossier: dict, analyse_id: str | None, user_id: str) -> None:
        self._dossier = dossier
        self._analyse_id = analyse_id
        self._name = ""
        self._description = ""
        self._definitions: dict[str, Any] | None = None
        self._elements = AnalysisProposer(dossier_id=dossier["id"], user_id=user_id, model=None, source_message_id=None)

    async def load(self) -> None:
        await self._elements.load()
        if not self._analyse_id:
            return
        try:
            async with async_session_factory() as db:
                analyse = await AnalyseRepository(db).get(uuid.UUID(self._analyse_id))
                if analyse is not None:
                    self._name, self._description = analyse.name, analyse.description or ""
                    self._definitions = build_internal_analyse(analyse).model_dump(mode="json")
        except Exception:
            logger.warning("Analyse %s illisible", self._analyse_id, exc_info=True)

    @property
    def available(self) -> bool:
        return self._definitions is not None

    @property
    def elements_available(self) -> bool:
        return self._elements.available

    def owns(self, name: str) -> bool:
        return name in (READ_ANALYSIS, LIST_AGENTS, READ_AGENT_OUTPUT)

    def definitions(self) -> list[dict]:
        return list(DEFINITIONS) if self.available else []

    def view_elements(self) -> str:
        return self._elements.list_elements()

    def read_analysis(self) -> str:
        if self._definitions is None:
            return "L'analyse de ce dossier est indisponible."
        classification, extraction = self._definitions["classification"], self._definitions["extraction"]
        lines = [f"Analyse « {self._name} »"]
        if self._description:
            lines.append(f"Objectif : {self._description}")
        lines.append(f"\nClassification{' (plusieurs labels possibles)' if classification['multi_label'] else ''} :")
        lines.append(f"Consigne : {classification['prompt'] or '(aucune)'}")
        lines.extend(f"- {label['name']} : {label['definition']}" for label in classification["labels"])
        lines.append("\nExtraction d'entités :")
        lines.append(f"Consigne : {extraction['prompt'] or '(aucune)'}")
        lines.extend(
            f"- {entity['name']} ({entity['type']}) : {entity['definition']}" for entity in extraction["entities"]
        )
        lines.append(f"\n{self.list_agents()}")
        return "\n".join(lines)

    def list_agents(self) -> str:
        agents = (self._definitions or {}).get("agents", [])
        if not agents:
            return "Cette analyse n'a pas d'agent."
        lines = ["Agents de l'analyse :"]
        for agent in agents:
            role = " ".join(agent["prompt"].split())
            tools = ", ".join(agent["tools"]) or "aucun outil choisi"
            lines.append(f"- {agent['name']} ({tools}) : {role[:200]}")
        return "\n".join(lines)

    def read_agent_output(self, name: str) -> str:
        wanted = name.strip().casefold()
        for step in self._dossier.get("execution_steps", []):
            if step.get("kind") == "agent" and str(step.get("label", "")).casefold() == wanted:
                output = step.get("output")
                if not output:
                    return f"L'agent « {step['label']} » n'a pas encore produit de synthèse sur ce dossier."
                return output[:OUTPUT_CHARS] + ("…" if len(output) > OUTPUT_CHARS else "")
        return f"Aucune synthèse de l'agent « {name} » sur ce dossier. {self.list_agents()}"

    def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        if name == READ_ANALYSIS:
            return self.read_analysis()
        if name == LIST_AGENTS:
            return self.list_agents()
        return self.read_agent_output(str(arguments.get("agent", "")))
