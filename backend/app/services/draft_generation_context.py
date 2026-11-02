from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_draft import DocumentDraft
from app.repositories.document_draft_repository import DocumentDraftRepository, template_definitions
from app.repositories.dossier_note_repository import DossierNoteRepository
from app.repositories.dossier_repository import DossierRepository
from app.schemas.document_draft import (
    InternalDraftContextOut,
    InternalDraftNoteOut,
    InternalElementOut,
    InternalFieldOut,
)
from app.services import generation_prompt
from app.services.document_fields import load_revision_elements


async def build_draft_context(db: AsyncSession, draft: DocumentDraft) -> InternalDraftContextOut:
    """Ce qu'il faut à l'agent pour générer : champs et états courants, éléments de la **révision figée** du
    brouillon, notes internes non archivées, métadonnées du dossier et prompt en vigueur."""
    repository = DocumentDraftRepository(db)
    template_version = await repository.template_version(draft)
    current = await repository.current_versions(draft.id)
    dossier = await DossierRepository(db).get(draft.dossier_id)
    prompt_number, prompt = await generation_prompt.current(db)
    notes = await DossierNoteRepository(db).list(draft.dossier_id)

    def day(moment) -> str | None:  # noqa: ANN001
        return moment.date().isoformat() if moment else None

    return InternalDraftContextOut(
        draft_id=draft.id,
        dossier_id=draft.dossier_id,
        status=draft.status,
        requested_by=draft.generation_requested_by,
        template_name=template_version.name,
        generation_instructions=template_version.generation_instructions,
        fields=[
            InternalFieldOut(
                name=d.name,
                label=d.label,
                type=d.type,
                required=d.required,
                instruction=d.instruction,
                source=d.source.model_dump(),
                status=current[d.name].status,
                value=current[d.name].value,
                origin=current[d.name].origin,
            )
            for d in template_definitions(template_version)
        ],
        elements=[
            InternalElementOut(
                id=e.element.id,
                version_id=e.version.id,
                kind=e.element.kind,
                name=e.element.definition_name,
                text=e.text,
                page=e.element.first_page_number,
                document_id=e.element.document_id,
            )
            for e in await load_revision_elements(db, draft.revision_id)
        ],
        notes=[
            InternalDraftNoteOut(id=n.id, version_number=n.current.version_number, content=n.current.content)
            for n in notes
        ],
        metadata={
            "dossier_name": dossier.name if dossier else None,
            "dossier_created_at": day(dossier.created_at) if dossier else None,
            "dossier_started_at": day(dossier.started_at) if dossier else None,
            "dossier_ended_at": day(dossier.ended_at) if dossier else None,
        },
        prompt_version_number=prompt_number,
        prompt_label=generation_prompt.version_label(prompt_number),
        prompt=prompt,
    )
