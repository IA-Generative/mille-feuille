import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import get_current_user
from app.db import get_db
from app.models.analyse import Analyse, VersionedField
from app.repositories.analyse_repository import AnalyseRepository
from app.schemas.analyse import Version
from app.schemas.search_settings import SearchSettingsOut
from app.services.search import settings as search_settings
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
        locked=await repository.has_indexed_dossier(analyse.id),
        versions=[
            Version(id=v.id, content=SearchSettings.model_validate(v.content), created_at=v.created_at)
            for v in repository.field_versions(analyse, VersionedField.SEARCH_SETTINGS)
        ],
    )


async def _refuse_if_locked(repository: AnalyseRepository, analyse: Analyse) -> None:
    if await repository.has_indexed_dossier(analyse.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "reglages_verrouilles",
                "message": "Un dossier de l'analyse est déjà indexé : les réglages de recherche ne changent plus.",
            },
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
    """Remplace les réglages. Tant qu'aucun dossier de l'analyse n'est indexé ; l'état précédent est conservé dans
    l'historique."""
    repository = AnalyseRepository(db)
    analyse = await _analyse_or_404(repository, analyse_id)
    await _refuse_if_locked(repository, analyse)
    await repository.update_search_settings(analyse, body.model_dump())
    return await _out(repository, analyse)


@router.post("/{analyse_id}/search-settings/restore/{version_id}", response_model=SearchSettingsOut)
async def restore_search_settings(
    analyse_id: uuid.UUID, version_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> SearchSettingsOut:
    """Restaure des réglages antérieurs ; les réglages courants deviennent eux-mêmes une version."""
    repository = AnalyseRepository(db)
    analyse = await _analyse_or_404(repository, analyse_id)
    await _refuse_if_locked(repository, analyse)
    version = repository.search_settings_version(analyse, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Version introuvable")
    await repository.update_search_settings(analyse, SearchSettings.model_validate(version.content).model_dump())
    return await _out(repository, analyse)
