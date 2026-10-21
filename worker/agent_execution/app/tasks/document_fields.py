"""Tâche de génération des valeurs de champs d'un brouillon de document (issue #141, parent #107).

Déposée **sur demande** de l'instructeur (jamais seule). Le worker lit le brouillon, la révision **figée** de
l'analyse, les notes internes et le prompt en vigueur ; il demande au LLM une valeur par champ à renseigner, puis
dépose chacune comme **proposition** (jamais validée). Une valeur déjà validée n'est jamais réécrite ; une
information absente laisse le champ tel quel (« non renseigné »), jamais inventée. Le résultat est signalé sur le
brouillon : terminé (propositions, champs sans valeur trouvée, contexte tronqué) ou échec avec la raison.
"""

import logging

from app import api_client, document_generation, llm, usage
from app.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.generate_document_fields", bind=True)
def generate_document_fields(
    self, draft_id: str, names: list[str] | None = None, instruction: str | None = None
) -> None:
    """``names`` limite les champs (régénération) ; ``instruction`` est la consigne facultative de l'instructeur."""
    usage.bind("generate_document_fields")
    with api_client.get_client() as client:
        count = 0
        missing: list[str] = []
        truncated = False
        prompt_label: str | None = None
        try:
            context = api_client.get_draft_context(client, draft_id)
            prompt_label = context["prompt_label"]
            if context["status"] != "brouillon":
                api_client.finish_draft_generation(
                    client, draft_id, status="échec", error="Ce brouillon n'est plus modifiable."
                )
                return
            targets = document_generation.select_targets(context, names)
            # L'instruction ne vaut que pour une régénération ciblée (un seul champ).
            regeneration = instruction if names is not None and len(targets) == 1 else None

            for batch in document_generation.batches(targets, settings.GENERATION_FIELDS_PER_CALL):
                built = document_generation.build_context(
                    context,
                    batch,
                    max_tokens=settings.GENERATION_MAX_CONTEXT_TOKENS,
                    max_item_chars=settings.GENERATION_MAX_ITEM_CHARS,
                    regeneration_instruction=regeneration,
                )
                truncated = truncated or built.truncated
                result = llm.generate_field_values(document_generation.build_messages(context["prompt"], built))
                interpreted = document_generation.interpret(result, batch, built)
                missing.extend(interpreted.missing)
                for name, (value, sources) in interpreted.proposals.items():
                    outcome = api_client.propose_draft_field(
                        client,
                        draft_id,
                        name,
                        {
                            "value": value,
                            "sources": sources,
                            "prompt_version": prompt_label,
                            "model": settings.LLM_MODEL,
                            "instruction": regeneration,
                        },
                    )
                    if outcome == "ok":
                        count += 1
                    else:
                        # « validated » : validé entre-temps, on n'y touche pas ; « invalid » : valeur du mauvais type.
                        logger.info("Proposal for field %s of draft %s skipped: %s", name, draft_id, outcome)
                        if outcome == "invalid":
                            missing.append(name)

            api_client.finish_draft_generation(
                client,
                draft_id,
                status="terminé",
                proposal_count=count,
                missing=missing,
                truncated=truncated,
                prompt_version=prompt_label,
            )
            logger.info(
                "Draft %s generated: %d proposal(s), %d missing, truncated=%s", draft_id, count, len(missing), truncated
            )
        except Exception as error:
            logger.exception("Generation failed for draft %s", draft_id)
            try:
                api_client.finish_draft_generation(
                    client,
                    draft_id,
                    status="échec",
                    proposal_count=count,
                    missing=missing,
                    truncated=truncated,
                    prompt_version=prompt_label,
                    error=str(error),
                )
            except Exception:
                logger.warning("Could not report the failure of draft %s", draft_id, exc_info=True)
            raise
