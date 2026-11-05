"""Génération des valeurs de champs d'un brouillon de document (issue #141, parent #107).

Lancée **sur demande** de l'instructeur (jamais seule). L'agent lit le brouillon, la révision **figée** de l'analyse,
les notes internes et le prompt en vigueur ; il demande au LLM une valeur par champ à renseigner, puis dépose chacune
comme **proposition** (jamais validée). Une valeur déjà validée n'est jamais réécrite ; une information absente laisse
le champ tel quel (« non renseigné »), jamais inventée. Le résultat est signalé sur le brouillon : terminé
(propositions, champs sans valeur trouvée, contexte tronqué) ou échec avec la raison."""

import logging
import uuid

from app.agent import document_generation, llm, model_router, usage
from app.agent.runner import settings
from app.db import async_session_factory
from app.repositories.document_draft_repository import (
    GENERATION_DONE,
    GENERATION_FAILED,
    DocumentDraftRepository,
    DraftError,
    UnknownFieldError,
    ValidatedFieldError,
    template_definitions,
)
from app.services.document_fields import FieldValueError
from app.services.draft_generation_context import build_draft_context

logger = logging.getLogger(__name__)


async def generate_document_fields(
    draft_id: str, names: list[str] | None = None, instruction: str | None = None
) -> None:
    """``names`` limite les champs (régénération) ; ``instruction`` est la consigne facultative de l'instructeur."""
    usage.bind("generate_document_fields")
    async with async_session_factory() as db:
        repository = DocumentDraftRepository(db)
        draft = await repository.get_by_id(uuid.UUID(draft_id))
        if draft is None:
            logger.warning("Brouillon %s introuvable, génération ignorée", draft_id)
            return
        count = 0
        missing: list[str] = []
        truncated = False
        prompt_label: str | None = None
        try:
            context = (await build_draft_context(db, draft)).model_dump(mode="json")
            prompt_label = context["prompt_label"]
            if context["status"] != "brouillon":
                await repository.finish_generation(
                    draft,
                    status=GENERATION_FAILED,
                    proposal_count=None,
                    missing=[],
                    truncated=False,
                    prompt_version=None,
                    error="Ce brouillon n'est plus modifiable.",
                )
                return
            definitions = {d.name: d for d in template_definitions(await repository.template_version(draft))}
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
                result = await llm.generate_field_values(document_generation.build_messages(context["prompt"], built))
                interpreted = document_generation.interpret(result, batch, built)
                missing.extend(interpreted.missing)
                for name, (value, sources) in interpreted.proposals.items():
                    try:
                        await repository.propose(
                            draft,
                            definitions[name],
                            value,
                            sources=sources,
                            prompt_version=prompt_label,
                            model=await model_router.for_difficulty(3),
                            instruction=regeneration,
                        )
                        count += 1
                    except ValidatedFieldError:
                        # Validé entre-temps : on n'y touche pas.
                        logger.info("Proposal for field %s of draft %s skipped: validated", name, draft_id)
                    except (DraftError, FieldValueError, UnknownFieldError) as error:
                        # Valeur du mauvais type : le champ reste à renseigner.
                        logger.info("Proposal for field %s of draft %s skipped: %s", name, draft_id, error)
                        await db.rollback()
                        missing.append(name)

            await repository.finish_generation(
                draft,
                status=GENERATION_DONE,
                proposal_count=count,
                missing=missing,
                truncated=truncated,
                prompt_version=prompt_label,
                error=None,
            )
            logger.info(
                "Draft %s generated: %d proposal(s), %d missing, truncated=%s", draft_id, count, len(missing), truncated
            )
        except Exception as error:
            logger.exception("Generation failed for draft %s", draft_id)
            await db.rollback()
            await repository.finish_generation(
                draft,
                status=GENERATION_FAILED,
                proposal_count=count,
                missing=missing,
                truncated=truncated,
                prompt_version=prompt_label,
                error=str(error)[:2000],
            )
