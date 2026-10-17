"""Tests des modèles de structured output de la classification."""

import pytest

from app.llm import ClassificationResult, LabelPrediction, MultiLabelClassificationResult


def test_label_prediction_model() -> None:
    pred = LabelPrediction(label_name="CNI", confidence=0.95, reasoning="Photo visible")
    assert pred.label_name == "CNI"
    assert pred.confidence == 0.95
    assert pred.reasoning == "Photo visible"


def test_classification_result_model() -> None:
    pred = LabelPrediction(label_name="Facture", confidence=0.8)
    result = ClassificationResult(prediction=pred)
    assert result.prediction.label_name == "Facture"
    assert result.prediction.confidence == 0.8


def test_multi_label_classification_result_model() -> None:
    result = MultiLabelClassificationResult(
        predictions=[
            LabelPrediction(label_name="CNI", confidence=0.9),
            LabelPrediction(label_name="RIB", confidence=0.4),
        ]
    )
    assert [p.label_name for p in result.predictions] == ["CNI", "RIB"]


def test_source_section_gives_the_name_and_description_in_context() -> None:
    from app.llm import source_section

    assert source_section(None) == ""
    assert source_section({"name": "", "description": "x"}) == ""
    assert source_section({"name": "Guichet", "description": "En main propre"}) == (
        "--- Source du document ---\nGuichet : En main propre\n\n"
    )
    assert source_section({"name": "Guichet", "description": "  "}) == "--- Source du document ---\nGuichet\n\n"


def test_client_applies_the_hub_timeout_and_retries_of_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import llm

    monkeypatch.setattr(llm.settings, "OPENAI_API_KEY", "cle-de-test")
    monkeypatch.setattr(llm.settings, "OPENAI_API_BASE_URL", "http://hub.test/v1")
    monkeypatch.setattr(llm.settings, "OPENAI_TIMEOUT_SECONDS", 7.5)
    monkeypatch.setattr(llm.settings, "OPENAI_MAX_RETRIES", 1)

    client = llm._client()

    assert client.timeout == 7.5
    assert client.max_retries == 1
