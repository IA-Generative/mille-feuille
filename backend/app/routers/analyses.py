import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import KeycloakSettings, SharingSettings
from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.models.analyse import (
    Agent,
    Analyse,
    EntityDefinition,
    LabelDefinition,
    VersionedField,
)
from app.models.analyse_share import AnalyseShareKind
from app.repositories.analyse_repository import AnalyseRepository, StatusInUseError, StatusValidationError
from app.repositories.document_source_repository import DocumentSourceRepository, SourceNameTakenError
from app.schemas.analyse import (
    AgentCreate,
    AgentOut,
    AnalyseCreate,
    AnalyseListItem,
    AnalyseOut,
    AnalyseShareCreate,
    AnalyseShareOut,
    CustomFieldOut,
    CustomFieldsUpdate,
    DueSettingsIn,
    DueSettingsOut,
    EntitiesUpdate,
    LabelsUpdate,
    ModelUpdate,
    OutputUpdate,
    PromptUpdate,
    StatusDefinitionOut,
    StatusesRestore,
    StatusesUpdate,
    ToolsUpdate,
)
from app.schemas.document_source import DocumentSourceIn, DocumentSourceOut
from app.schemas.pagination import Page
from app.services.tools.agent_tools import ToolsRefusedError, validate_agent_tools

router = APIRouter(prefix="/analyses", tags=["Analyses"], dependencies=[Depends(get_current_user)])

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
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(description="Recherche par nom (insensible à la casse)")] = None,
) -> Page[AnalyseListItem]:
    repository = AnalyseRepository(db)
    analyses, total = await repository.list_paginated(page=page, page_size=page_size, q=q)
    items = [
        AnalyseListItem(
            id=a.id,
            name=a.name,
            description=a.description,
            created_at=a.created_at,
            agent_count=len(a.agents),
            statuses=[StatusDefinitionOut.model_validate(s) for s in a.statuses],
        )
        for a in analyses
    ]
    return Page.of(items, total=total, page=page, page_size=page_size)


@router.post("", response_model=AnalyseOut, status_code=status.HTTP_201_CREATED)
async def create_analyse(body: AnalyseCreate, db: Annotated[AsyncSession, Depends(get_db)]) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await repository.create(name=body.name, description=body.description)
    analyse = await _get_or_404(repository, analyse.id)
    return repository.to_schema(analyse)


@router.get("/{analyse_id}", response_model=AnalyseOut)
async def get_analyse(analyse_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    return repository.to_schema(analyse)


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
) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    labels = [LabelDefinition(name=lbl.name, definition=lbl.definition) for lbl in body.labels]
    await repository.update_classification_labels(analyse, labels)
    return repository.to_schema(analyse)


@router.post(
    "/{analyse_id}/classification/labels/restore/{version_id}",
    response_model=AnalyseOut,
)
async def restore_classification_labels(
    analyse_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    await repository.restore_field_version(analyse, VersionedField.CLASSIFICATION_LABELS, version_id)
    return repository.to_schema(analyse)


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
) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    entities = [EntityDefinition(name=ent.name, definition=ent.definition, type=ent.type) for ent in body.entities]
    await repository.update_extraction_entities(analyse, entities)
    return repository.to_schema(analyse)


@router.post("/{analyse_id}/extraction/entities/restore/{version_id}", response_model=AnalyseOut)
async def restore_extraction_entities(
    analyse_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalyseOut:
    repository = AnalyseRepository(db)
    analyse = await _get_or_404(repository, analyse_id)
    await repository.restore_field_version(analyse, VersionedField.EXTRACTION_ENTITIES, version_id)
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
):
    repository = AnalyseRepository(db)
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
