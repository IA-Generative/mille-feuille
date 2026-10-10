"""Outil du chat pour les notes internes du dossier.

Quand l'instructeur demande explicitement d'ajouter une note (« note que… », « ajoute une note »), le chat la dépose
dans les notes internes du dossier. Une note est **interne** (jamais visible de l'usager), **versionnée** et se modifie
ou s'archive ensuite depuis la vue de l'analyse : on l'enregistre donc tout de suite, sans carte de confirmation. À la
différence d'une proposition (analysis_tools), elle ne touche pas à l'analyse.
"""

import logging
from dataclasses import dataclass, field

import httpx

from app import api_client

logger = logging.getLogger(__name__)

# Limite par réponse : une demande d'ajout de note vaut une note, pas une rafale.
MAX_NOTES_PER_ANSWER = 3


@dataclass
class NoteWriter:
    client: httpx.Client
    dossier_id: str
    user_id: str
    max_notes: int = MAX_NOTES_PER_ANSWER
    note_ids: list[str] = field(default_factory=list, init=False)
    _added: set[str] = field(default_factory=set, init=False, repr=False)

    def add(self, content: str) -> str:
        """Ajoute une note interne. Renvoie le message destiné au LLM."""
        text = content.strip()
        if not text:
            return "Le contenu de la note est obligatoire."
        key = " ".join(text.casefold().split())
        if key in self._added:
            return "Cette note a déjà été ajoutée dans cette réponse : ne la répète pas et réponds à l'utilisateur."
        if len(self.note_ids) >= self.max_notes:
            return f"Limite atteinte : {self.max_notes} notes au maximum par réponse."
        try:
            note = api_client.create_dossier_note(self.client, self.dossier_id, text, f"chat-agent:{self.user_id}")
        except httpx.HTTPStatusError as error:
            logger.warning("Note refused for dossier %s: %s", self.dossier_id, error.response.status_code)
            return "La note n'a pas pu être enregistrée."
        self._added.add(key)
        self.note_ids.append(note["id"])
        return (
            "Note enregistrée dans les notes internes du dossier (visible dans la vue de l'analyse, modifiable). "
            "Dis simplement à l'utilisateur que tu l'as ajoutée, sans la répéter une seconde fois."
        )
