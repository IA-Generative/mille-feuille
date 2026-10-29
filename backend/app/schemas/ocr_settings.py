from pydantic import BaseModel

from app.schemas.analyse import Version


class OcrSettings(BaseModel):
    """Réglages de la lecture des documents scannés d'une analyse."""

    # Modèle du hub qui décrit les images et les tableaux. Absent : celui de la plateforme (`VLM_MODEL`).
    caption_model: str | None = None


class OcrSettingsOut(BaseModel):
    settings: OcrSettings
    versions: list[Version[OcrSettings]] = []


class InternalOcrSettingsOut(BaseModel):
    """Ce que le worker document_process lit pour un document : le modèle qui décrit ses images (None : le défaut)."""

    caption_model: str | None = None
