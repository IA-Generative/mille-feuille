"""Outil du chat pour les notes internes du dossier.

Quand l'instructeur demande explicitement d'ajouter une note (« note que… », « ajoute une note »), le chat la dépose
dans les notes internes du dossier. Une note est **interne** (jamais visible de l'usager), **versionnée** et se modifie
ou s'archive ensuite depuis la vue de l'analyse : on l'enregistre donc tout de suite, sans carte de confirmation. À la
différence d'une proposition (analysis_tools), elle ne touche pas à l'analyse.
"""

import logging
import uuid
from dataclasses import dataclass, field

from app.db import async_session_factory
from app.repositories.dossier_note_repository import DossierNoteRepository
from app.repositories.dossier_repository import DossierRepository

logger = logging.getLogger(__name__)

# Limite par réponse : une demande d'ajout de note vaut une note, pas une rafale.
MAX_NOTES_PER_ANSWER = 3


@dataclass
class NoteWriter:
    dossier_id: str
    user_id: str
    max_notes: int = MAX_NOTES_PER_ANSWER
    note_ids: list[str] = field(default_factory=list, init=False)
    _added: set[str] = field(default_factory=set, init=False, repr=False)

    async def add(self, content: str) -> str:
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
            async with async_session_factory() as db:
                dossier_id = uuid.UUID(self.dossier_id)
                if await DossierRepository(db).get(dossier_id) is None:
                    return "La note n'a pas pu être enregistrée."
                note = await DossierNoteRepository(db).create(
                    dossier_id, content=text, user_id=f"chat-agent:{self.user_id}"
                )
        except Exception:
            logger.warning("Note refused for dossier %s", self.dossier_id, exc_info=True)
            return "La note n'a pas pu être enregistrée."
        self._added.add(key)
        self.note_ids.append(str(note.id))
        return (
            "Note enregistrée dans les notes internes du dossier (visible dans la vue de l'analyse, modifiable). "
            "Dis simplement à l'utilisateur que tu l'as ajoutée, sans la répéter une seconde fois."
        )
