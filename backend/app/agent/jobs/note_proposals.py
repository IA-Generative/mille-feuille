"""Analyse d'une note interne (issue #117, parent #106).

Lancée **sur demande** de l'instructeur (jamais à l'ajout ou à la modification d'une note). L'agent lit la note et
l'analyse courante du dossier, demande au LLM les mises à jour que la note affirme explicitement, puis dépose chacune
comme **proposition en attente** : rien n'est appliqué, l'utilisateur accepte, modifie ou rejette (#114). Le résultat
est signalé sur la note (terminé avec le nombre de propositions, ou échec avec la raison)."""

import logging
import uuid

from app.agent import llm, model_router, usage
from app.agent.analysis_tools import AnalysisProposer
from app.db import async_session_factory
from app.repositories.dossier_note_repository import NOTE_ANALYSIS_DONE, NOTE_ANALYSIS_FAILED, DossierNoteRepository

logger = logging.getLogger(__name__)

# Version du prompt d'analyse de note (métriques d'acceptation, #102).
NOTE_PROMPT_VERSION = "note-v1"
# Une note ne doit pas noyer l'utilisateur de propositions.
MAX_PROPOSALS_PER_NOTE = 10


async def _finish(note_id: str, *, status: str, proposal_count: int | None = None, error: str | None = None) -> None:
    async with async_session_factory() as db:
        repository = DossierNoteRepository(db)
        note = await repository.get_by_id(uuid.UUID(note_id))
        if note is not None:
            await repository.finish_analysis(
                note, status=status, proposal_count=proposal_count, error=error[:2000] if error else None
            )


async def propose_from_note(note_id: str) -> None:
    usage.bind("propose_from_note")
    try:
        async with async_session_factory() as db:
            note = await DossierNoteRepository(db).get_by_id(uuid.UUID(note_id))
            if note is None:
                logger.warning("Note %s introuvable, analyse ignorée", note_id)
                return
            dossier_id, requested_by, archived = str(note.dossier_id), note.analysis_requested_by, note.archived
            content = note.current.content
        usage.bind("propose_from_note", user_id=requested_by, dossier_id=dossier_id)
        if archived:
            await _finish(note_id, status=NOTE_ANALYSIS_FAILED, error="Cette note est archivée.")
            return
        proposer = AnalysisProposer(
            dossier_id=dossier_id,
            user_id=requested_by or "",
            model=await model_router.default_model(),
            source_message_id=note_id,
            source_type="note",
            actor="note-agent",
            prompt_version=NOTE_PROMPT_VERSION,
            max_proposals=MAX_PROPOSALS_PER_NOTE,
        )
        await proposer.load()
        if not proposer.available:
            await _finish(note_id, status=NOTE_ANALYSIS_FAILED, error="Ce dossier n'a pas d'analyse à mettre à jour.")
            return

        result = await llm.propose_updates_from_note(note=content, elements=proposer.list_elements())
        for update in result.updates:
            before = len(proposer.proposal_ids)
            message = await proposer.propose(
                value=update.value,
                reason=update.reason,
                element_id=update.element_id,
                kind=update.kind,
                name=update.name,
            )
            if len(proposer.proposal_ids) == before:
                # Élément inconnu, valeur vide, limite atteinte ou refus.
                logger.info("Update from note %s skipped: %s", note_id, message)

        count = len(proposer.proposal_ids)
        await _finish(note_id, status=NOTE_ANALYSIS_DONE, proposal_count=count)
        logger.info("Note %s analysed: %d proposal(s)", note_id, count)
    except Exception as error:
        logger.exception("Note analysis failed for note %s", note_id)
        try:
            await _finish(note_id, status=NOTE_ANALYSIS_FAILED, error=str(error))
        except Exception:
            logger.warning("Could not report the failure of note %s", note_id, exc_info=True)
