import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import KeycloakSettings, SharingSettings
from app.connectors import s3_connector
from app.core.analyse_guard import require_analyse_visible
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.models.analyse import (
    Agent,
    Analyse,
    LabelDefinition,
    LabelExample,
    VersionedField,
)
from app.models.analyse_share import AnalyseShareKind
from app.models.analyse_theme import AnalyseTheme
from app.models.dossier import Dossier
from app.repositories.analyse_repository import (
    AnalyseRepository,
    DefinitionValidationError,
    EntityInput,
    StatusInUseError,
    StatusValidationError,
)
from app.repositories.document_source_repository import DocumentSourceRepository, SourceNameTakenError
from app.schemas.analyse import (
    AgentCreate,
    AgentOut,
    AnalyseCreate,
    AnalyseListItem,
    AnalyseOut,
    AnalyseShareCreate,
    AnalyseShareOut,
    AnalyseUpdate,
    CustomFieldOut,
    CustomFieldsUpdate,
    DueSettingsIn,
    DueSettingsOut,
    EntitiesUpdate,
    LabelExampleOut,
    LabelsUpdate,
    ModelUpdate,
    OutputUpdate,
    PromptUpdate,
    StatusDefinitionOut,
    StatusesRestore,
    StatusesUpdate,
    ToolsUpdate,
)
from app.schemas.analyse_theme import AnalyseThemeAssignment
from app.schemas.document_source import DocumentSourceIn, DocumentSourceOut
from app.schemas.pagination import Page
from app.services.analyse_creation import creation_groups, grant_groups
from app.services.tools.agent_tools import ToolsRefusedError, validate_agent_tools

router = APIRouter(
    prefix="/analyses",
    tags=["Analyses"],
    dependencies=[Depends(get_current_user), Depends(require_analyse_visible)],
)

# Route de partage publique (lien magique par email) : volontairement sur un
# routeur séparé, sans Depends(get_current_user) - la personne qui ouvre le
# lien n'a pas forcément de compte Keycloak. Monté sous le même préfixe
# /analyses dans main.py ; pas de collision avec GET /analyses/{analyse_id}
# (un seul segment) puisque ce chemin en a deux (shared/{token}).
public_router = APIRouter(prefix="/analyses", tags=["Analyses"])


async def _get_or_404(repository: AnalyseRepository, analyse_id: uuid.UUID) -> Analyse:
    analyse = await repository.get(analyse_id)
    if analyse is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analyse introuvable")
    return analyse


async def _definitions_or_422(operation) -> None:
    """Attend une modification de labels ou d'entités ; une liste qui ne respecte pas les règles donne un 422."""
    try:
        await operation
    except DefinitionValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


async def _validated_tools(
    db: AsyncSession, user: RequestContext, tool_ids: list[str], *, already: list[str] | None = None
) -> list[str]:
    """Les outils demandés pour un agent, sans doublon ; 422 `tools_refuses` si la personne ne peut pas les donner."""
    try:
        return await validate_agent_tools(db, user, tool_ids, already=already or [])
    except ToolsRefusedError as error:
        detail = {"code": "tools_refuses", "message": error.message, "tools": [r.id for r in error.refused]}
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail) from error


def _get_agent_or_404(repository: AnalyseRepository, analyse: Analyse, agent_id: uuid.UUID) -> Agent:
    agent = repository.get_agent(analyse, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent introuvable")
    return agent


def _status_error(error: Exception) -> HTTPException:
    """Traduit une erreur sur les statuts en réponse HTTP : 422 (règle non respectée) ou 409 (statut
    supprimé encore utilisé : le détail liste les statuts et le nombre de dossiers concernés)."""
    if isinstance(error, StatusInUseError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "status_in_use", "message": str(error), "statuses": error.in_use},
        )
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.get("", response_model=Page[AnalyseListItem])
async def list_analyses(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(description="Recherche dans le nom ou la description")] = None,
    theme_id: Annotated[uuid.UUID | None, Query(description="Analyses de ce thème")] = None,
    unthemed: Annotated[bool, Query(description="Analyses sans thème")] = False,
) -> Page[AnalyseListItem]:
    repository = AnalyseRepository(db)
    analyses, total = await repository.list_paginated(
        page=page, page_size=page_size, q=q, theme_id=theme_id, unthemed=unthemed, user=user
    )
    items = [
        AnalyseListItem(
            id=a.id,
            name=a.name,
            description=a.description,
            created_by=a.created_by,
            created_at=a.created_at,
            agent_count=len(a.agents),
            theme_id=a.theme_id,
            statuses=[StatusDefinitionOut.model_validate(s) for s in a.statuses],
        )
        for a in analyses
    ]
    return Page.of(items, total=total, page=page, page_size=page_size)


@router.post("", response_model=AnalyseOut, status_code=status.HTTP_201_CREATED)
async def create_analyse(
    body: AnalyseCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AnalyseOut:
    group_ids = await creation_groups(db, user, body.group_ids)
    repository = AnalyseRepository(db)
    analyse = await repository.create(name=body.name, description=body.description, created_by=user.user_id or None)
    await grant_groups(db, analyse.id, group_ids, user.user_id)
    analyse = await _get_or_404(repository, analyse.id)
    return repository.to_schema(analyse)


@router.get("/{analyse_id}", response_model=AnalyseOut)
async def get_analyse(analyse_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    return repository.to_schema(analyse)


@router.put("/{analyse_id}", response_model=AnalyseOut)
async def update_analyse(
    analyse_id: uuid.UUID,
    body: AnalyseUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AnalyseOut:
    """Remplace le nom et la description (le créateur et les administrateurs). Ce qui change est conservé dans
    l'historique (restaurable). La description sert d'instruction aux agents : elle compte comme une nouvelle version
    de l'analyse, pas le nom."""
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    await repository.update_identity(analyse, name=body.name, description=body.description)
    return repository.to_schema(analyse)


async def _restore_identity(
    analyse_id: uuid.UUID, field: VersionedField, version_id: uuid.UUID, db: AsyncSession, user: RequestContext
) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    version = repository.identity_version(analyse, field, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version introuvable")
    restored = str(version.content)
    await repository.update_identity(
        analyse,
        name=restored if field is VersionedField.NAME else analyse.name,
        description=restored if field is VersionedField.DESCRIPTION else analyse.description,
    )
    return repository.to_schema(analyse)


@router.post("/{analyse_id}/name/restore/{version_id}", response_model=AnalyseOut)
async def restore_name_version(
    analyse_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AnalyseOut:
    """Restaure un ancien nom ; le nom courant devient lui-même une version."""
    return await _restore_identity(analyse_id, VersionedField.NAME, version_id, db, user)


@router.post("/{analyse_id}/description/restore/{version_id}", response_model=AnalyseOut)
async def restore_description_version(
    analyse_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AnalyseOut:
    """Restaure une ancienne description ; la description courante devient elle-même une version."""
    return await _restore_identity(analyse_id, VersionedField.DESCRIPTION, version_id, db, user)


async def _theme_or_404(db: AsyncSession, theme_id: uuid.UUID) -> AnalyseTheme:
    theme = await db.get(AnalyseTheme, theme_id)
    if theme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thème introuvable")
    return theme


@router.put("/{analyse_id}/theme", response_model=AnalyseOut)
async def update_analyse_theme(
    analyse_id: uuid.UUID,
    body: AnalyseThemeAssignment,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AnalyseOut:
    """Range l'analyse dans un thème, ou aucun (le créateur et les administrateurs)."""
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    theme = await _theme_or_404(db, body.theme_id) if body.theme_id else None
    await repository.update_theme(analyse, theme)
    return repository.to_schema(await _get_or_404(repository, analyse_id))


@router.post("/{analyse_id}/theme/restore/{version_id}", response_model=AnalyseOut)
async def restore_theme_assignment(
    analyse_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AnalyseOut:
    """Remet l'analyse dans un thème précédent ; 404 si ce thème a été supprimé depuis."""
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    version = repository.identity_version(analyse, VersionedField.THEME, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version introuvable")
    previous = version.content["theme_id"]
    theme = await _theme_or_404(db, uuid.UUID(previous)) if previous else None
    await repository.update_theme(analyse, theme)
    return repository.to_schema(await _get_or_404(repository, analyse_id))


@router.delete("/{analyse_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analyse(
    analyse_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> Response:
    """Supprime l'analyse avec son contenu (agents, labels, statuts, historique, partages, modèles de document).
    Refusée (409) tant qu'elle a des dossiers : on ne perd jamais un dossier par ce chemin."""
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    dossier_count = await db.scalar(select(func.count()).select_from(Dossier).where(Dossier.analyse_id == analyse_id))
    if dossier_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cette analyse a encore {dossier_count} dossier(s) : elle ne peut pas être supprimée.",
        )
    try:
        await repository.delete(analyse)
    except IntegrityError as error:  # un dossier créé entre le comptage et la suppression
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Des dossiers référencent encore cette analyse."
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{analyse_id}/sources", response_model=list[DocumentSourceOut])
async def list_analyse_sources(analyse_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    """Le catalogue de sources de fichiers de l'analyse : proposées au dépôt d'un fichier dans ses dossiers."""
    await _get_or_404(AnalyseRepository(db), analyse_id)
    return await DocumentSourceRepository(db).list_for_analyse(analyse_id)


@router.post("/{analyse_id}/sources", response_model=DocumentSourceOut, status_code=status.HTTP_201_CREATED)
async def create_analyse_source(
    analyse_id: uuid.UUID, body: DocumentSourceIn, db: Annotated[AsyncSession, Depends(get_db)]
):
    """Ajoute une source au catalogue de l'analyse. Pas de versionnage : modifier ou supprimer est définitif."""
    await _get_or_404(AnalyseRepository(db), analyse_id)
    try:
        return await DocumentSourceRepository(db).create(
            name=body.name, description=body.description, analyse_id=analyse_id
        )
    except SourceNameTakenError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Une source porte déjà ce nom") from error


@router.put("/{analyse_id}/classification/prompt", response_model=AnalyseOut)
async def update_classification_prompt(
    analyse_id: uuid.UUID,
    body: PromptUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    await repository.update_classification_prompt(analyse, body.prompt)
    return repository.to_schema(analyse)


@router.post(
    "/{analyse_id}/classification/prompt/restore/{version_id}",
    response_model=AnalyseOut,
)
async def restore_classification_prompt(
    analyse_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    await repository.restore_field_version(analyse, VersionedField.CLASSIFICATION_PROMPT, version_id)
    return repository.to_schema(analyse)


@router.put("/{analyse_id}/classification/labels", response_model=AnalyseOut)
async def update_classification_labels(
    analyse_id: uuid.UUID,
    body: LabelsUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    labels = [LabelDefinition(id=lbl.id, name=lbl.name, definition=lbl.definition) for lbl in body.labels]
    await _definitions_or_422(repository.update_classification_labels(analyse, labels))
    return repository.to_schema(analyse)


@router.post(
    "/{analyse_id}/classification/labels/restore/{version_id}",
    response_model=AnalyseOut,
)
async def restore_classification_labels(
    analyse_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    await _definitions_or_422(
        repository.restore_field_version(analyse, VersionedField.CLASSIFICATION_LABELS, version_id)
    )
    return repository.to_schema(analyse)


# --- Documents d'exemple d'un label ---

MAX_EXAMPLES_PER_LABEL = 10
MAX_EXAMPLE_SIZE = 10 * 1024 * 1024
EXAMPLE_TYPES = {"image/png", "image/jpeg", "image/webp", "application/pdf"}


def _label_or_404(analyse: Analyse, label_id: uuid.UUID) -> LabelDefinition:
    label = next((label for label in analyse.labels if label.id == label_id), None)
    if label is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label introuvable")
    return label


def _example_or_404(label: LabelDefinition, example_id: uuid.UUID) -> LabelExample:
    example = next((example for example in label.examples if example.id == example_id), None)
    if example is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exemple introuvable")
    return example


@router.get("/{analyse_id}/classification/labels/{label_id}/examples", response_model=list[LabelExampleOut])
async def list_label_examples(
    analyse_id: uuid.UUID, label_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> list[LabelExampleOut]:
    analyse = await _get_or_404(AnalyseRepository(db), analyse_id)
    return [LabelExampleOut.model_validate(example) for example in _label_or_404(analyse, label_id).examples]


@router.post(
    "/{analyse_id}/classification/labels/{label_id}/examples",
    response_model=list[LabelExampleOut],
    status_code=status.HTTP_201_CREATED,
)
async def add_label_examples(
    analyse_id: uuid.UUID,
    label_id: uuid.UUID,
    files: Annotated[list[UploadFile], File()],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> list[LabelExampleOut]:
    """Ajoute des documents d'exemple au label (PDF, PNG, JPEG ou WebP, 10 Mo au plus, 10 par label). Tout ou rien :
    un fichier refusé n'en laisse entrer aucun."""
    analyse = await _get_or_404(AnalyseRepository(db), analyse_id)
    label = _label_or_404(analyse, label_id)
    if len(label.examples) + len(files) > MAX_EXAMPLES_PER_LABEL:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{MAX_EXAMPLES_PER_LABEL} exemples au plus par label.",
        )
    contents: list[tuple[str, str, bytes]] = []
    for upload in files:
        name = (upload.filename or "exemple").rsplit("/", 1)[-1]
        if upload.content_type not in EXAMPLE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"« {name} » : format non pris en charge (PDF, PNG, JPEG ou WebP).",
            )
        data = await upload.read(MAX_EXAMPLE_SIZE + 1)
        if len(data) > MAX_EXAMPLE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"« {name} » : plus de {MAX_EXAMPLE_SIZE // (1024 * 1024)} Mo.",
            )
        contents.append((name, upload.content_type, data))

    created: list[LabelExample] = []
    for name, content_type, data in contents:
        example_id = uuid.uuid4()
        key = f"analyses/{analyse_id}/label-examples/{example_id}-{name}"
        await run_in_threadpool(s3_connector.upload, key, data, content_type)
        created.append(
            LabelExample(
                id=example_id, label_id=label.id, name=name, content_type=content_type, size=len(data), s3_key=key
            )
        )
    try:
        db.add_all(created)
        await db.commit()
    except Exception:
        await db.rollback()
        for example in created:
            await run_in_threadpool(s3_connector.delete, example.s3_key)
        raise
    return [LabelExampleOut.model_validate(example) for example in created]


@router.get("/{analyse_id}/classification/labels/{label_id}/examples/{example_id}/file")
async def get_label_example_file(
    analyse_id: uuid.UUID,
    label_id: uuid.UUID,
    example_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    analyse = await _get_or_404(AnalyseRepository(db), analyse_id)
    example = _example_or_404(_label_or_404(analyse, label_id), example_id)
    data, content_type = await run_in_threadpool(s3_connector.download, example.s3_key)
    return Response(content=data, media_type=content_type)


@router.delete(
    "/{analyse_id}/classification/labels/{label_id}/examples/{example_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_label_example(
    analyse_id: uuid.UUID,
    label_id: uuid.UUID,
    example_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> Response:
    """Retire un exemple. Les zones tracées dessus gardent leur rectangle mais ne désignent plus d'exemple."""
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    example = _example_or_404(_label_or_404(analyse, label_id), example_id)
    repository.forget_examples_in_zones(analyse, {example.id})
    key = example.s3_key
    await db.delete(example)
    await db.commit()
    await run_in_threadpool(s3_connector.delete, key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{analyse_id}/extraction/prompt", response_model=AnalyseOut)
async def update_extraction_prompt(
    analyse_id: uuid.UUID,
    body: PromptUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    await repository.update_extraction_prompt(analyse, body.prompt)
    return repository.to_schema(analyse)


@router.post("/{analyse_id}/extraction/prompt/restore/{version_id}", response_model=AnalyseOut)
async def restore_extraction_prompt(
    analyse_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    await repository.restore_field_version(analyse, VersionedField.EXTRACTION_PROMPT, version_id)
    return repository.to_schema(analyse)


@router.put("/{analyse_id}/extraction/entities", response_model=AnalyseOut)
async def update_extraction_entities(
    analyse_id: uuid.UUID,
    body: EntitiesUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    entities = [
        EntityInput(
            id=ent.id,
            name=ent.name,
            definition=ent.definition,
            type=ent.type,
            nature=ent.nature,
            label_ids=ent.label_ids,
            zones=[zone.model_dump(mode="json") for zone in ent.zones],
        )
        for ent in body.entities
    ]
    await _definitions_or_422(repository.update_extraction_entities(analyse, entities))
    return repository.to_schema(analyse)


@router.post("/{analyse_id}/extraction/entities/restore/{version_id}", response_model=AnalyseOut)
async def restore_extraction_entities(
    analyse_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    await _definitions_or_422(repository.restore_field_version(analyse, VersionedField.EXTRACTION_ENTITIES, version_id))
    return repository.to_schema(analyse)


@router.post("/{analyse_id}/agents", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def add_agent(
    analyse_id: uuid.UUID,
    body: AgentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AgentOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    tools = await _validated_tools(db, user, body.tools)
    agent = await repository.add_agent(
        analyse,
        name=body.name,
        prompt=body.prompt,
        tools=tools,
        output=body.output,
        model=body.model,
    )
    analyse = await _get_or_404(repository, analyse_id)
    return repository.to_agent_schema(analyse, repository.get_agent(analyse, agent.id))


@router.get("/{analyse_id}/statuses", response_model=list[StatusDefinitionOut])
async def list_statuses(
    analyse_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> list[StatusDefinitionOut]:
    """Statuts de dossier de l'analyse, dans l'ordre (issue #168)."""
    analyse = await _get_or_404(AnalyseRepository(db), analyse_id)
    return [StatusDefinitionOut.model_validate(s) for s in analyse.statuses]


@router.put("/{analyse_id}/statuses", response_model=AnalyseOut)
async def update_statuses(
    analyse_id: uuid.UUID,
    body: StatusesUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AnalyseOut:
    """Remplace la liste des statuts. Un statut conserve son identité si son ``id`` est fourni ; un statut
    supprimé encore utilisé exige un remplaçant (``replacements``), sinon 409. L'état précédent est
    conservé dans ``statuses_versions``."""
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    try:
        await repository.update_statuses(analyse, body.statuses, body.replacements, actor=user)
    except (StatusValidationError, StatusInUseError) as error:
        raise _status_error(error) from error
    return repository.to_schema(analyse)


@router.post("/{analyse_id}/statuses/restore/{version_id}", response_model=AnalyseOut)
async def restore_statuses(
    analyse_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    body: StatusesRestore | None = None,
) -> AnalyseOut:
    """Restaure une version antérieure des statuts. Si la restauration supprime des statuts utilisés par
    des dossiers, les remplaçants se donnent dans ``replacements`` (sinon 409)."""
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    try:
        restored = await repository.restore_statuses_version(
            analyse, version_id, body.replacements if body else None, actor=user
        )
    except (StatusValidationError, StatusInUseError) as error:
        raise _status_error(error) from error
    if not restored:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version introuvable")
    return repository.to_schema(analyse)


@router.get("/{analyse_id}/due-settings", response_model=DueSettingsOut)
async def get_due_settings(analyse_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> DueSettingsOut:
    """Durée par défaut et seuils de couleur de l'échéance des dossiers de l'analyse (issue #172)."""
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    return DueSettingsOut.model_validate(repository.due_settings_snapshot(analyse))


@router.put("/{analyse_id}/due-settings", response_model=AnalyseOut)
async def update_due_settings(
    analyse_id: uuid.UUID, body: DueSettingsIn, db: Annotated[AsyncSession, Depends(get_db)]
) -> AnalyseOut:
    """Remplace la durée par défaut et les seuils de couleur. L'état précédent est conservé dans
    ``due_settings_versions`` (restaurable). Les dossiers ne sont pas modifiés : leur niveau est calculé à la
    lecture."""
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    await repository.update_due_settings(analyse, body)
    return repository.to_schema(analyse)


@router.post("/{analyse_id}/due-settings/restore/{version_id}", response_model=AnalyseOut)
async def restore_due_settings(
    analyse_id: uuid.UUID, version_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    if not await repository.restore_due_settings_version(analyse, version_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version introuvable")
    return repository.to_schema(analyse)


def _require_admin(user: RequestContext) -> None:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Seuls les administrateurs définissent les colonnes du suivi."
        )


@router.get("/{analyse_id}/custom-fields", response_model=list[CustomFieldOut])
async def get_custom_fields(
    analyse_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> list[CustomFieldOut]:
    """Colonnes personnalisées du suivi de l'analyse (issue #173)."""
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    return [CustomFieldOut.model_validate(field) for field in repository.custom_fields_snapshot(analyse)]


@router.put("/{analyse_id}/custom-fields", response_model=AnalyseOut)
async def update_custom_fields(
    analyse_id: uuid.UUID,
    body: CustomFieldsUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AnalyseOut:
    """Remplace les colonnes personnalisées (administrateurs). L'état précédent est conservé dans
    ``custom_fields_versions`` (restaurable). Un champ sans ``id`` est nouveau ; un champ supprimé garde ses valeurs
    sauf ``purge_removed`` ; un champ dont le type change perd ses valeurs."""
    _require_admin(user)
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    await repository.update_custom_fields(analyse, body)
    return repository.to_schema(analyse)


@router.post("/{analyse_id}/custom-fields/restore/{version_id}", response_model=AnalyseOut)
async def restore_custom_fields(
    analyse_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AnalyseOut:
    _require_admin(user)
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    if not await repository.restore_custom_fields_version(analyse, version_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version introuvable")
    return repository.to_schema(analyse)


@router.put("/{analyse_id}/agents/{agent_id}/prompt", response_model=AgentOut)
async def update_agent_prompt(
    analyse_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: PromptUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    agent = _get_agent_or_404(repository, analyse, agent_id)
    await repository.update_agent_prompt(analyse, agent, body.prompt)
    return repository.to_agent_schema(analyse, agent)


@router.post(
    "/{analyse_id}/agents/{agent_id}/prompt/restore/{version_id}",
    response_model=AgentOut,
)
async def restore_agent_prompt(
    analyse_id: uuid.UUID,
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    agent = _get_agent_or_404(repository, analyse, agent_id)
    await repository.restore_field_version(analyse, VersionedField.AGENT_PROMPT, version_id, agent)
    return repository.to_agent_schema(analyse, agent)


@router.put("/{analyse_id}/agents/{agent_id}/tools", response_model=AgentOut)
async def update_agent_tools(
    analyse_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: ToolsUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AgentOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    agent = _get_agent_or_404(repository, analyse, agent_id)
    tools = await _validated_tools(db, user, body.tools, already=agent.tools)
    await repository.update_agent_tools(analyse, agent, tools)
    return repository.to_agent_schema(analyse, agent)


@router.post(
    "/{analyse_id}/agents/{agent_id}/tools/restore/{version_id}",
    response_model=AgentOut,
)
async def restore_agent_tools(
    analyse_id: uuid.UUID,
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    agent = _get_agent_or_404(repository, analyse, agent_id)
    await repository.restore_field_version(analyse, VersionedField.AGENT_TOOLS, version_id, agent)
    return repository.to_agent_schema(analyse, agent)


@router.put("/{analyse_id}/agents/{agent_id}/output", response_model=AgentOut)
async def update_agent_output(
    analyse_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: OutputUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    agent = _get_agent_or_404(repository, analyse, agent_id)
    await repository.update_agent_output(analyse, agent, body.output)
    return repository.to_agent_schema(analyse, agent)


@router.post(
    "/{analyse_id}/agents/{agent_id}/output/restore/{version_id}",
    response_model=AgentOut,
)
async def restore_agent_output(
    analyse_id: uuid.UUID,
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    agent = _get_agent_or_404(repository, analyse, agent_id)
    await repository.restore_field_version(analyse, VersionedField.AGENT_OUTPUT, version_id, agent)
    return repository.to_agent_schema(analyse, agent)


@router.put("/{analyse_id}/agents/{agent_id}/model", response_model=AgentOut)
async def update_agent_model(
    analyse_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: ModelUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    agent = _get_agent_or_404(repository, analyse, agent_id)
    await repository.update_agent_model(analyse, agent, body.model)
    return repository.to_agent_schema(analyse, agent)


@router.post(
    "/{analyse_id}/agents/{agent_id}/model/restore/{version_id}",
    response_model=AgentOut,
)
async def restore_agent_model(
    analyse_id: uuid.UUID,
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    agent = _get_agent_or_404(repository, analyse, agent_id)
    await repository.restore_field_version(analyse, VersionedField.AGENT_MODEL, version_id, agent)
    return repository.to_agent_schema(analyse, agent)


# --- Partage ---


@router.get("/{analyse_id}/shares", response_model=Page[AnalyseShareOut])
async def list_shares(
    analyse_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[AnalyseShareOut]:
    repository = AnalyseRepository(db)
    await _get_or_404(repository, analyse_id)
    shares, total = await repository.list_shares_paginated(analyse_id=analyse_id, page=page, page_size=page_size)
    return Page.of(list(shares), total=total, page=page, page_size=page_size)


@router.post(
    "/{analyse_id}/shares",
    response_model=AnalyseShareOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_share(
    analyse_id: uuid.UUID,
    body: AnalyseShareCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)

    if body.kind == AnalyseShareKind.EMAIL:
        if not body.email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email requis")
        ttl = body.expires_in_hours or SharingSettings().SHARE_DEFAULT_TTL_HOURS
        share, token = await repository.create_email_share(
            analyse, email=body.email, expires_in_hours=ttl, created_by=user.user_id
        )
        frontend_url = KeycloakSettings().FRONTEND_URL
        result = AnalyseShareOut.model_validate(share)
        result.share_url = f"{frontend_url}/analyses/shared/{token}"
        return result

    if not body.keycloak_group:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="keycloak_group requis")
    share = await repository.create_group_share(analyse, keycloak_group=body.keycloak_group, created_by=user.user_id)
    return AnalyseShareOut.model_validate(share)


@router.delete("/{analyse_id}/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share(
    analyse_id: uuid.UUID,
    share_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
):
    repository = AnalyseRepository(db)
    await _get_or_404(repository, analyse_id)
    share = await repository.get_share_by_id(analyse_id, share_id)
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partage introuvable")
    await repository.revoke_share(share)


@public_router.get("/shared/{token}", response_model=AnalyseOut)
async def get_shared_analyse(token: str, db: Annotated[AsyncSession, Depends(get_db)]):
    repository = AnalyseRepository(db)
    analyse = await repository.get_by_share_token(token)
    if analyse is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lien de partage invalide ou expiré",
        )
    return repository.to_schema(analyse)
