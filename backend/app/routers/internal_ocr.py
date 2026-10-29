import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.internal import verify_app_token
from app.db import get_db
from app.models.analyse import Analyse
from app.models.dossier import Dossier
from app.schemas.ocr_settings import InternalOcrSettingsOut, OcrSettings

router = APIRouter(prefix="/internal", tags=["Internal", "OCR"], dependencies=[Depends(verify_app_token)])


@router.get("/dossiers/{dossier_id}/ocr-settings", response_model=InternalOcrSettingsOut)
async def get_ocr_settings(
    dossier_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> InternalOcrSettingsOut:
    """Réglages de lecture des documents scannés à appliquer au dossier : ceux de son analyse. Un dossier « à ranger »
    n'en a pas encore, donc les défauts de la plateforme."""
    dossier = await db.get(Dossier, dossier_id)
    if dossier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")
    analyse = await db.get(Analyse, dossier.analyse_id) if dossier.analyse_id else None
    if analyse is None:
        return InternalOcrSettingsOut()
    return InternalOcrSettingsOut(caption_model=OcrSettings.model_validate(analyse.ocr_settings).caption_model)
