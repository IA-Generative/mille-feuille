import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _visual_classification_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les tests ne chargent jamais CLIP (plusieurs secondes et ~600 Mo) : ceux de la classification visuelle
    l'activent explicitement et remplacent `clip.classify_image`."""
    monkeypatch.setattr(settings, "CLIP_ENABLED", False)
