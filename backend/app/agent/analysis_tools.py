"""Outils du chat pour l'analyse de dossier (issue #115, parent #106).

Le chat peut **proposer** de modifier l'analyse du dossier quand l'instructeur
apporte une information (« la pièce est valide, vérifiée par téléphone »). Une
proposition n'applique **rien** : elle est déposée en attente et l'utilisateur
l'accepte, la modifie ou la rejette dans le chat (ou dans la vue de
l'analyse). Ce module ne crée jamais de version lui-même.
"""

import logging
import uuid
from dataclasses import dataclass, field
from urllib.parse import quote

from app.db import async_session_factory
from app.models.dossier_analysis import DossierAnalysisStatus
from app.repositories.analysis_proposal_repository import AnalysisProposalRepository, ProposalTargetError
from app.repositories.dossier_analysis_repository import DossierAnalysisRepository
from app.schemas.analysis_proposal import InternalProposalCreateIn
from app.schemas.dossier_analysis import InvalidElementValueError

logger = logging.getLogger(__name__)

# Version du prompt du chat qui produit ces propositions : permet de mesurer
# le taux d'acceptation par version (journal des décisions, #114 et #102).
PROMPT_VERSION = "chat-v2"
# Limite par réponse : pas plus de propositions que d'informations clairement
# exprimées, pour ne pas noyer l'utilisateur.
MAX_PROPOSALS_PER_ANSWER = 5

# Types d'éléments qu'on peut proposer en texte ; une relation relie deux
# éléments et se saisit dans la vue de l'analyse.
_VALUE_KEY = {"classification": "label", "entity": "value", "field": "value", "synthesis": "text"}


def proposals_marker(analysis_id: str, proposal_ids: list[str]) -> str:
    """Marqueur ajouté en fin de réponse (commentaire HTML invisible) que le
    frontend transforme en cartes de proposition. Ajouté par l'agent, pas
    par le LLM, pour rester fiable."""
    return f"\n\n<!--analysis-proposals:{quote(analysis_id, safe='')}:{','.join(proposal_ids)}-->"


@dataclass
class AnalysisProposer:
    """Accès du chat à l'analyse du dossier : lister les éléments, déposer des
    propositions pour le compte de l'utilisateur de la conversation.

    `load()` lit l'analyse une fois, avant que le modèle ne parle : `available` et les définitions d'outils qui en
    dépendent sont synchrones."""

    dossier_id: str
    user_id: str
    model: str | None
    source_message_id: str | None
    # D'où viennent les propositions : le chat (message source) ou l'analyse
    # d'une note (#117). ``actor`` préfixe l'auteur enregistré, ``prompt_version``
    # sert aux métriques d'acceptation, ``max_proposals`` borne le bruit.
    source_type: str = "chat_message"
    actor: str = "chat-agent"
    prompt_version: str = PROMPT_VERSION
    max_proposals: int = MAX_PROPOSALS_PER_ANSWER
    _analysis: dict | None = field(default=None, init=False, repr=False)
    analysis_id: str | None = field(default=None, init=False)
    proposal_ids: list[str] = field(default_factory=list, init=False)
    # Propositions déjà déposées pendant cette réponse (cible, valeur) : le LLM rappelle parfois l'outil avec la
    # même information jusqu'à la limite, ce qui affichait cinq cartes identiques.
    _proposed: set[tuple] = field(default_factory=set, init=False, repr=False)

    async def load(self) -> None:
        try:
            async with async_session_factory() as db:
                analyses = DossierAnalysisRepository(db)
                analysis = await analyses.get_current(uuid.UUID(self.dossier_id))
                self._analysis = (await analyses.build_out(analysis)).model_dump(mode="json") if analysis else None
        except Exception:
            logger.warning("Could not load the analysis of dossier %s", self.dossier_id, exc_info=True)

    @property
    def available(self) -> bool:
        """Le dossier a-t-il une analyse (donc quelque chose à proposer) ?"""
        return self._analysis is not None

    def list_elements(self) -> str:
        analysis = self._analysis
        if analysis is None:
            return "Ce dossier n'a pas encore d'analyse."
        elements = analysis.get("elements", [])
        if not elements:
            return "L'analyse du dossier ne contient encore aucun élément."
        lines = [f"{len(elements)} élément(s) dans l'analyse du dossier :\n"]
        for element in elements:
            version = element.get("retained_version") or {}
            value = _text(element["kind"], version.get("value") or {})
            name = element.get("definition_name") or element["kind"]
            flag = " [à revoir]" if element.get("needs_review") else ""
            lines.append(f"- id={element['id']} | {element['kind']} | {name} = {value}{flag}")
        return "\n".join(lines)

    async def propose(
        self,
        *,
        value: str,
        reason: str,
        element_id: str | None = None,
        kind: str | None = None,
        name: str | None = None,
    ) -> str:
        """Dépose une proposition en attente. Renvoie le message destiné au LLM."""
        analysis = self._analysis
        if analysis is None:
            return "Impossible de proposer : ce dossier n'a pas encore d'analyse."
        if len(self.proposal_ids) >= self.max_proposals:
            return f"Limite atteinte : {self.max_proposals} propositions au maximum."
        if not value.strip() or not reason.strip():
            return "La valeur et le motif sont obligatoires."

        if element_id:
            element = next((e for e in analysis["elements"] if e["id"] == element_id), None)
            if element is None:
                return "Élément introuvable : appelle view_analysis pour obtenir les identifiants valides."
            kind = element["kind"]
        elif not kind:
            return "Indique soit element_id (modifier un élément), soit kind et name (en ajouter un)."
        if kind not in _VALUE_KEY:
            return (
                "Les relations ne peuvent pas être proposées ici : l'utilisateur les saisit dans l'analyse du dossier."
            )

        key = (element_id or (kind, (name or "").strip().lower()), value.strip().casefold())
        if key in self._proposed:
            return (
                "Cette proposition existe déjà dans cette réponse : ne la répète pas. N'appelle plus propose_update "
                "pour cette information et réponds à l'utilisateur."
            )

        body = {
            "proposed_by": f"{self.actor}:{self.user_id}",
            "value": {_VALUE_KEY[kind]: value.strip()},
            "reason": reason.strip(),
            "source_type": self.source_type if self.source_message_id else None,
            "source_id": self.source_message_id,
            "model": self.model,
            "prompt_version": self.prompt_version,
        }
        if element_id:
            body["element_id"] = element_id
        else:
            body["kind"] = kind
            body["definition_name"] = name
        try:
            proposal_id = await self._create(body)
        except (ProposalTargetError, InvalidElementValueError, _Frozen, ValueError) as error:
            logger.warning("Proposal refused for dossier %s: %s", self.dossier_id, error)
            return f"La proposition a été refusée : {error}"
        self.analysis_id = analysis["id"]
        self.proposal_ids.append(proposal_id)
        self._proposed.add(key)
        return (
            "Proposition enregistrée, EN ATTENTE de confirmation de l'utilisateur : rien n'est modifié tant qu'il "
            "ne l'a pas acceptée. Dis-lui simplement que tu lui proposes cette modification, sans affirmer qu'elle "
            "est appliquée. Ne la propose pas une seconde fois."
        )

    async def _create(self, body: dict) -> str:
        data = InternalProposalCreateIn(**body)
        async with async_session_factory() as db:
            analyses = DossierAnalysisRepository(db)
            analysis = await analyses.get_current(uuid.UUID(self.dossier_id))
            if analysis is None:
                raise _Frozen("Aucune analyse pour ce dossier")
            if analysis.status == DossierAnalysisStatus.FIGEE:
                raise _Frozen("Cette analyse est figée")
            proposal = await AnalysisProposalRepository(analyses).create(
                analysis,
                proposed_by=data.proposed_by,
                value=data.value,
                reason=data.reason,
                element_id=data.element_id,
                kind=data.kind,
                definition_name=data.definition_name,
                source_type=data.source_type,
                source_id=data.source_id,
                model=data.model,
                prompt_version=data.prompt_version,
            )
            return str(proposal.id)


class _Frozen(Exception):
    """L'analyse n'existe plus ou est figée : rien ne peut lui être proposé."""


def _text(kind: str, value: dict) -> str:
    key = {"classification": "label", "entity": "value", "field": "value", "synthesis": "text"}.get(kind)
    if key:
        return str(value.get(key, ""))
    return str(value)
