"""Tests des modèles de structured output de la classification."""

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
