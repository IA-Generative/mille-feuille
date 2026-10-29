import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import get_current_user
from app.db import get_db
from app.models.analyse import Analyse, VersionedField
from app.repositories.analyse_repository import AnalyseRepository
from app.schemas.analyse import Version
from app.schemas.ocr_settings import OcrSettings, OcrSettingsOut

router = APIRouter(prefix="/analyses", tags=["OCR"], dependencies=[Depends(get_current_user)])


async def _analyse_or_404(repository: AnalyseRepository, analyse_id: uuid.UUID) -> Analyse:
    analyse = await repository.get(analyse_id)
    if analyse is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analyse introuvable")
    return analyse


def _out(repository: AnalyseRepository, analyse: Analyse) -> OcrSettingsOut:
    return OcrSettingsOut(
        settings=OcrSettings.model_validate(analyse.ocr_settings),
        versions=[
            Version(id=v.id, content=OcrSettings.model_validate(v.content), created_at=v.created_at)
            for v in repository.field_versions(analyse, VersionedField.OCR_SETTINGS)
        ],
    )


@router.get("/{analyse_id}/ocr-settings", response_model=OcrSettingsOut)
async def get_ocr_settings(analyse_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> OcrSettingsOut:
    """Les réglages de lecture des documents scannés de l'analyse et leur historique."""
    repository = AnalyseRepository(db)
    return _out(repository, await _analyse_or_404(repository, analyse_id))


@router.put("/{analyse_id}/ocr-settings", response_model=OcrSettingsOut)
async def update_ocr_settings(
    analyse_id: uuid.UUID, body: OcrSettings, db: Annotated[AsyncSession, Depends(get_db)]
) -> OcrSettingsOut:
    """Remplace les réglages ; l'état précédent est conservé dans l'historique. Ils valent pour les documents
    extraits ensuite : ceux qui l'ont déjà été gardent leurs descriptions."""
    repository = AnalyseRepository(db)
    analyse = await _analyse_or_404(repository, analyse_id)
    await repository.update_ocr_settings(analyse, body.model_dump())
    return _out(repository, analyse)


@router.post("/{analyse_id}/ocr-settings/restore/{version_id}", response_model=OcrSettingsOut)
async def restore_ocr_settings(
    analyse_id: uuid.UUID, version_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> OcrSettingsOut:
    """Restaure des réglages antérieurs ; les réglages courants deviennent eux-mêmes une version."""
    repository = AnalyseRepository(db)
    analyse = await _analyse_or_404(repository, analyse_id)
    version = repository.ocr_settings_version(analyse, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Version introuvable")
    await repository.update_ocr_settings(analyse, OcrSettings.model_validate(version.content).model_dump())
    return _out(repository, analyse)
