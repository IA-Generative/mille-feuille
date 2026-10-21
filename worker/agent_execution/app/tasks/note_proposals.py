"""Tâche d'analyse d'une note interne (issue #117, parent #106).

Déposée **sur demande** de l'instructeur (jamais à l'ajout ou à la modification
d'une note). Le worker lit la note et l'analyse courante du dossier, demande au
LLM les mises à jour que la note affirme explicitement, puis dépose chacune
comme **proposition en attente** : rien n'est appliqué, l'utilisateur accepte,
modifie ou rejette (#114). Le résultat est signalé sur la note (terminé avec le
nombre de propositions, ou échec avec la raison).
"""

import logging

from app import api_client, llm, usage
from app.analysis_tools import AnalysisProposer
from app.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)

# Version du prompt d'analyse de note (métriques d'acceptation, #102).
NOTE_PROMPT_VERSION = "note-v1"
# Une note ne doit pas noyer l'utilisateur de propositions.
MAX_PROPOSALS_PER_NOTE = 10


@celery_app.task(name="app.tasks.propose_from_note", bind=True)
def propose_from_note(self, note_id: str) -> None:
    usage.bind("propose_from_note")
    with api_client.get_client() as client:
        try:
            note = api_client.get_note(client, note_id)
            usage.bind(
                "propose_from_note", user_id=note.get("analysis_requested_by"), dossier_id=note.get("dossier_id")
            )
            if note.get("archived"):
                api_client.finish_note_analysis(client, note_id, status="échec", error="Cette note est archivée.")
                return
            proposer = AnalysisProposer(
                client=client,
                dossier_id=note["dossier_id"],
                user_id=note.get("analysis_requested_by") or "",
                model=settings.LLM_MODEL,
                source_message_id=note_id,
                source_type="note",
                actor="note-agent",
                prompt_version=NOTE_PROMPT_VERSION,
                max_proposals=MAX_PROPOSALS_PER_NOTE,
            )
            if not proposer.available:
                api_client.finish_note_analysis(
                    client, note_id, status="échec", error="Ce dossier n'a pas d'analyse à mettre à jour."
                )
                return

            result = llm.propose_updates_from_note(note=note["content"], elements=proposer.list_elements())
            for update in result.updates:
                before = len(proposer.proposal_ids)
                message = proposer.propose(
                    value=update.value,
                    reason=update.reason,
                    element_id=update.element_id,
                    kind=update.kind,
                    name=update.name,
                )
                if len(proposer.proposal_ids) == before:
                    # Élément inconnu, valeur vide, limite atteinte ou refus du serveur.
                    logger.info("Update from note %s skipped: %s", note_id, message)

            count = len(proposer.proposal_ids)
            api_client.finish_note_analysis(client, note_id, status="terminé", proposal_count=count)
            logger.info("Note %s analysed: %d proposal(s)", note_id, count)
        except Exception as error:
            logger.exception("Note analysis failed for note %s", note_id)
            try:
                api_client.finish_note_analysis(client, note_id, status="échec", error=str(error))
            except Exception:
                logger.warning("Could not report the failure of note %s", note_id, exc_info=True)
            raise
