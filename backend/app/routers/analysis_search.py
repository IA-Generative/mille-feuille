import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.models.analyse import Analyse, VersionedField
from app.repositories.analyse_repository import AnalyseRepository
from app.schemas.analyse import Version
from app.schemas.search_index import AnalyseIndexOverview, AnalyseRebuildOut
from app.schemas.search_settings import SearchSettingsOut, SearchSettingsPreviewOut
from app.services.search import settings as search_settings
from app.services.search.index_service import SearchIndexService, SettingsUnresolvedError
from app.services.search.settings import SearchSettings

router = APIRouter(prefix="/analyses", tags=["Search"], dependencies=[Depends(get_current_user)])


async def _analyse_or_404(repository: AnalyseRepository, analyse_id: uuid.UUID) -> Analyse:
    analyse = await repository.get(analyse_id)
    if analyse is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analyse introuvable")
    return analyse


async def _out(repository: AnalyseRepository, analyse: Analyse) -> SearchSettingsOut:
    effective, problem = None, None
    try:
        effective = search_settings.resolve(analyse.search_settings)
    except ValueError as error:
        problem = str(error)
    return SearchSettingsOut(
        settings=SearchSettings.model_validate(analyse.search_settings),
        effective=effective,
        fingerprint=effective.fingerprint if effective else None,
        problem=problem,
        overview=await SearchIndexService(repository.db).overview(analyse),
        versions=[
            Version(id=v.id, content=SearchSettings.model_validate(v.content), created_at=v.created_at)
            for v in repository.field_versions(analyse, VersionedField.SEARCH_SETTINGS)
        ],
    )


@router.get("/{analyse_id}/search-settings", response_model=SearchSettingsOut)
async def get_search_settings(analyse_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> SearchSettingsOut:
    """Les réglages de découpage et d'embeddings de l'analyse, leur résolution et leur historique."""
    repository = AnalyseRepository(db)
    return await _out(repository, await _analyse_or_404(repository, analyse_id))


@router.put("/{analyse_id}/search-settings", response_model=SearchSettingsOut)
async def update_search_settings(
    analyse_id: uuid.UUID, body: SearchSettings, db: Annotated[AsyncSession, Depends(get_db)]
) -> SearchSettingsOut:
    """Remplace les réglages ; l'état précédent est conservé dans l'historique. Les dossiers déjà indexés avec d'autres
    réglages deviennent obsolètes : ils gardent leur index (la recherche continue) jusqu'à leur reconstruction."""
    repository = AnalyseRepository(db)
    analyse = await _analyse_or_404(repository, analyse_id)
    await repository.update_search_settings(analyse, body.model_dump())
    return await _out(repository, analyse)


@router.post("/{analyse_id}/search-settings/restore/{version_id}", response_model=SearchSettingsOut)
async def restore_search_settings(
    analyse_id: uuid.UUID, version_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> SearchSettingsOut:
    """Restaure des réglages antérieurs ; les réglages courants deviennent eux-mêmes une version."""
    repository = AnalyseRepository(db)
    analyse = await _analyse_or_404(repository, analyse_id)
    version = repository.search_settings_version(analyse, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Version introuvable")
    await repository.update_search_settings(analyse, SearchSettings.model_validate(version.content).model_dump())
    return await _out(repository, analyse)


@router.post("/{analyse_id}/search-settings/preview", response_model=SearchSettingsPreviewOut)
async def preview_search_settings(
    analyse_id: uuid.UUID, body: SearchSettings, db: Annotated[AsyncSession, Depends(get_db)]
) -> SearchSettingsPreviewOut:
    """Ce qu'un changement de réglages ferait, sans l'enregistrer : combien de dossiers indexés deviendraient obsolètes
    (donc seraient à reconstruire), et si le découpage rappellerait un modèle d'IA."""
    repository = AnalyseRepository(db)
    analyse = await _analyse_or_404(repository, analyse_id)
    service = SearchIndexService(db)
    try:
        effective = search_settings.resolve(body.model_dump())
        problem = None
    except ValueError as error:
        effective, problem = None, str(error)
    try:
        current = search_settings.resolve(analyse.search_settings).fingerprint
    except ValueError:
        current = None
    overview = await service.overview(analyse, body.model_dump())
    return SearchSettingsPreviewOut(
        effective=effective,
        problem=problem,
        fingerprint=effective.fingerprint if effective else None,
        changes_index=effective is None or effective.fingerprint != current,
        obsolete_dossiers=overview.obsolete,
        indexed_dossiers=overview.indexed,
        uses_ai_chunking=body.strategy == search_settings.STRATEGY_AI,
    )


@router.get("/{analyse_id}/search-index", response_model=AnalyseIndexOverview)
async def get_analyse_search_index(
    analyse_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> AnalyseIndexOverview:
    """Les index de recherche des dossiers de l'analyse : à jour, obsolètes, en reconstruction, en attente."""
    repository = AnalyseRepository(db)
    return await SearchIndexService(db).overview(await _analyse_or_404(repository, analyse_id))


@router.post(
    "/{analyse_id}/search-index/rebuild", response_model=AnalyseRebuildOut, status_code=status.HTTP_202_ACCEPTED
)
async def rebuild_analyse_search_index(
    analyse_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[RequestContext, Depends(get_current_user)],
) -> AnalyseRebuildOut:
    """Reconstruit l'index de chaque dossier de l'analyse qui n'est plus à jour. Un nombre limité de reconstructions
    tournent en même temps : les autres attendent leur tour."""
    repository = AnalyseRepository(db)
    analyse = await _analyse_or_404(repository, analyse_id)
    service = SearchIndexService(db)
    try:
        created = await service.rebuild_analyse(analyse, user.user_id)
    except SettingsUnresolvedError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": "reglages_incomplets", "message": str(error)}
        ) from error
    return AnalyseRebuildOut(
        started=sum(1 for r in created if r.status == "building"),
        queued=sum(1 for r in created if r.status == "queued"),
        overview=await service.overview(analyse),
    )
