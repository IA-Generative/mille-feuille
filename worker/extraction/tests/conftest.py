import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _gliner_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les tests ne chargent jamais GLiNER (plusieurs secondes et ~1 Go) : ceux de l'extraction GLiNER l'activent
    explicitement et remplacent `gliner.extract`."""
    monkeypatch.setattr(settings, "GLINER_ENABLED", False)
