"""Les modèles éphémères doivent refléter les schémas du backend (../openapi.json)."""

from __future__ import annotations

import pytest
from contract import check
from pydantic import BaseModel

from millefeuille_ephemeral import models as m

CASES: list[tuple[type[BaseModel], str]] = [
    (m.EphemeralAnalysisConfig, "EphemeralAnalyseCreate"),
    (m.EphemeralAnalyseCreated, "EphemeralAnalyseCreated"),
    (m.EphemeralRunCreated, "EphemeralRunCreated"),
    (m.EphemeralAnalyse, "EphemeralAnalyseOut"),
    (m.EphemeralRun, "EphemeralRunOut"),
    (m.EphemeralRunSummary, "EphemeralRunSummary"),
    (m.EphemeralClassification, "EphemeralClassificationOut"),
    (m.EphemeralClassifiedDocument, "EphemeralClassifiedDocument"),
    (m.EphemeralClassifiedPage, "EphemeralClassifiedPage"),
    (m.EphemeralLabelResult, "EphemeralLabelResult"),
    (m.EphemeralExtraction, "EphemeralExtractionOut"),
    (m.EphemeralExtractedDocument, "EphemeralExtractedDocument"),
    (m.EphemeralExtractedPage, "EphemeralExtractedPage"),
    (m.EphemeralEntityResult, "EphemeralEntityResult"),
]


@pytest.mark.parametrize(("model", "schema"), CASES, ids=lambda v: v if isinstance(v, str) else v.__name__)
def test_model_matches_backend_schema(model: type[BaseModel], schema: str) -> None:
    assert check(model, schema) == []
