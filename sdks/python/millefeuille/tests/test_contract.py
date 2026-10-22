"""Les modèles du SDK doivent refléter exactement les schémas du backend (tests/../openapi.json)."""

from __future__ import annotations

import pytest
from contract import SCHEMAS, check
from pydantic import BaseModel

from millefeuille import models as m

OUTPUTS: list[tuple[type[BaseModel], str]] = [
    (m.LabelDefinition, "LabelDefinitionOut"),
    (m.EntityDefinition, "EntityDefinitionOut"),
    (m.Classification, "ClassificationOut"),
    (m.Extraction, "ExtractionOut"),
    (m.Agent, "AgentOut"),
    (m.AnalyseListItem, "AnalyseListItem"),
    (m.Analyse, "AnalyseOut"),
    (m.ExecutionLog, "ExecutionLogOut"),
    (m.ExecutionStep, "ExecutionStepOut"),
    (m.BoundingBox, "BoundingBoxOut"),
    (m.PredictionValidation, "PredictionValidationOut"),
    (m.Prediction, "DocumentPredictionSummaryOut"),
    (m.DocumentPage, "DocumentPageOut"),
    (m.Summary, "DossierSummaryOut"),
    (m.Summary, "DocumentSummaryOut"),
    (m.Document, "DossierDocumentOut"),
    (m.Dossier, "DossierOut"),
    (m.AppToken, "AppTokenOut"),
    (m.CreatedAppToken, "AppTokenCreated"),
    (m.LlmModel, "LlmModel"),
    (m.LlmModelsResponse, "LlmModelsResponse"),
]

INPUTS: list[tuple[type[BaseModel], str]] = [
    (m.LabelDefinitionIn, "LabelDefinitionIn"),
    (m.EntityDefinitionIn, "EntityDefinitionIn"),
    (m.AgentCreate, "AgentCreate"),
    (m.AnalyseCreate, "AnalyseCreate"),
    (m.DossierCreate, "DossierCreate"),
    (m.AppTokenCreate, "AppTokenCreate"),
]


@pytest.mark.parametrize(("model", "schema"), OUTPUTS + INPUTS, ids=lambda v: v if isinstance(v, str) else v.__name__)
def test_model_matches_backend_schema(model: type[BaseModel], schema: str) -> None:
    assert check(model, schema) == []


@pytest.mark.parametrize(
    ("enum_cls", "schema"),
    [
        (m.DossierStatus, "DossierStatus"),
        (m.ExecutionStepKind, "ExecutionStepKind"),
        (m.ExecutionStepStatus, "ExecutionStepStatus"),
        (m.ExecutionLogLevel, "ExecutionLogLevel"),
        (m.TextExtractionStatus, "TextExtractionStatus"),
        (m.SummaryStatus, "SummaryStatus"),
        (m.SuggestionStatus, "SuggestionStatus"),
        (m.PredictionKind, "PredictionKind"),
        (m.PredictionValidationStatus, "PredictionValidationStatus"),
        (m.EntityType, "EntityType"),
    ],
)
def test_enum_matches_backend(enum_cls: type, schema: str) -> None:
    assert [member.value for member in enum_cls] == SCHEMAS[schema]["enum"]
