"""Tests de la classification visuelle (CLIP) : tâche, module clip et empreinte."""

import httpx
import pytest
from test_tasks import _stub_classification, _UnitBackend

from app import clip, fingerprint
from app.config import settings
from app.llm import LabelPrediction, MultiLabelClassificationResult
from app.tasks import classification as classification_mod
from app.tasks.classification import classify_dossier

LABELS = [
    {"id": "l1", "name": "CNI", "definition": "Carte nationale d'identité"},
    {"id": "l2", "name": "RIB", "definition": ""},
]


@pytest.fixture
def visual(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Active la classification visuelle avec un CLIP simulé ; renvoie les appels reçus."""
    monkeypatch.setattr(settings, "CLIP_ENABLED", True)
    calls: list[dict] = []

    def classify_image(image_bytes, label_definitions, *, multi_label):
        calls.append({"image": image_bytes, "multi_label": multi_label})
        return [LabelPrediction(label_name="RIB", confidence=0.8)]

    monkeypatch.setattr(classification_mod.clip, "classify_image", classify_image)
    return calls


def test_visual_prediction_is_deposited_in_its_own_unit_with_the_visual_source(monkeypatch, visual) -> None:
    backend = _UnitBackend()
    backend.install(monkeypatch)
    _stub_classification(monkeypatch)

    classify_dossier.run("dossier-1")

    # Page 1 (avec capture) : unité textuelle + unité visuelle. Page 2 (sans capture) : textuelle seulement.
    assert [u["description"].get("source") for u in backend.declared] == [None, "visual", None]
    assert [(p["source"], p["unit_id"]) for p in backend.predictions] == [
        ("textual", "unit-1"),
        ("visual", "unit-2"),
        ("textual", "unit-3"),
    ]
    visual_prediction = backend.predictions[1]
    assert (visual_prediction["kind"], visual_prediction["name"], visual_prediction["confidence"]) == (
        "label",
        "RIB",
        0.8,
    )
    assert visual_prediction["label_definition_id"] is None  # RIB n'est pas défini dans l'analyse de test
    assert visual == [{"image": b"png", "multi_label": False}]


def test_a_failing_visual_classification_never_fails_the_textual_one(monkeypatch, visual) -> None:
    backend = _UnitBackend()
    backend.install(monkeypatch)
    _stub_classification(monkeypatch)

    def broken(*args, **kwargs):
        raise RuntimeError("image illisible")

    monkeypatch.setattr(classification_mod.clip, "classify_image", broken)

    classify_dossier.run("dossier-1")  # ne lève pas

    assert [p["source"] for p in backend.predictions] == ["textual", "textual"]
    assert ("unit-2", "échec") in backend.completed
    assert ("unit-1", "terminé") in backend.completed


def test_nothing_visual_happens_when_clip_is_disabled(monkeypatch) -> None:
    backend = _UnitBackend()
    backend.install(monkeypatch)
    _stub_classification(monkeypatch)

    classify_dossier.run("dossier-1")

    assert all(u["description"].get("source") is None for u in backend.declared)
    assert {p["source"] for p in backend.predictions} == {"textual"}


def test_a_reused_visual_unit_does_not_call_clip(monkeypatch, visual) -> None:
    first = _UnitBackend()
    first.install(monkeypatch)
    _stub_classification(monkeypatch)
    classify_dossier.run("dossier-1")
    fingerprints = [u["input_fingerprint"] for u in first.declared]
    visual.clear()

    again = _UnitBackend()
    again.reuse = {fp: [] for fp in fingerprints}
    again.install(monkeypatch)
    classify_dossier.run("dossier-1")

    assert visual == []
    assert again.predictions == []


def test_multi_label_is_passed_to_clip(monkeypatch, visual) -> None:
    class Multi(_UnitBackend):
        def handler(self, request):
            response = super().handler(request)
            if request.url.path.endswith("/analyses/analyse-1"):
                body = response.json()
                body["classification"]["multi_label"] = True
                return httpx.Response(200, json=body)
            return response

    backend = Multi()
    backend.install(monkeypatch)
    _stub_classification(monkeypatch)
    monkeypatch.setattr(
        classification_mod.llm,
        "classify_page",
        lambda **kwargs: MultiLabelClassificationResult(
            predictions=[LabelPrediction(label_name="CNI", confidence=0.9)]
        ),
    )

    classify_dossier.run("dossier-1")

    assert visual[0]["multi_label"] is True


# --- Module clip (probabilités simulées : le vrai modèle n'est jamais chargé) ---


def _with_probabilities(monkeypatch, probabilities: list[float]) -> None:
    monkeypatch.setattr(clip, "scores", lambda image_bytes, label_definitions: probabilities)


def test_clip_single_label_keeps_only_the_best_label(monkeypatch) -> None:
    _with_probabilities(monkeypatch, [0.3, 0.7])
    result = clip.classify_image(b"x", LABELS, multi_label=False)
    assert [(p.label_name, p.confidence) for p in result] == [("RIB", 0.7)]


def test_clip_multi_label_keeps_labels_above_the_threshold_best_first(monkeypatch) -> None:
    monkeypatch.setattr(settings, "CLIP_MULTI_LABEL_THRESHOLD", 0.25)
    _with_probabilities(monkeypatch, [0.3, 0.7])
    assert [p.label_name for p in clip.classify_image(b"x", LABELS, multi_label=True)] == ["RIB", "CNI"]
    _with_probabilities(monkeypatch, [0.1, 0.9])
    assert [p.label_name for p in clip.classify_image(b"x", LABELS, multi_label=True)] == ["RIB"]


def test_clip_multi_label_always_returns_the_best_label(monkeypatch) -> None:
    monkeypatch.setattr(settings, "CLIP_MULTI_LABEL_THRESHOLD", 0.9)
    _with_probabilities(monkeypatch, [0.6, 0.4])
    assert [p.label_name for p in clip.classify_image(b"x", LABELS, multi_label=True)] == ["CNI"]


def test_label_text_joins_name_and_definition() -> None:
    assert clip.label_text(LABELS[0]) == "CNI: Carte nationale d'identité"
    assert clip.label_text(LABELS[1]) == "RIB"


# --- Empreinte ---


PAGE = {"content": "texte", "screenshot_key": "screens/p1.png"}


def test_visual_fingerprint_ignores_the_text_but_not_the_screenshot_labels_or_model(monkeypatch) -> None:
    base = fingerprint.visual_classification_fingerprint(PAGE, LABELS)
    assert base == fingerprint.visual_classification_fingerprint({**PAGE, "content": "autre texte"}, LABELS)
    variants = {
        fingerprint.visual_classification_fingerprint({**PAGE, "screenshot_key": "screens/p2.png"}, LABELS),
        fingerprint.visual_classification_fingerprint(PAGE, LABELS[:1]),
        fingerprint.visual_classification_fingerprint(PAGE, LABELS, multi_label=True),
    }
    assert base not in variants and len(variants) == 3
    monkeypatch.setattr(fingerprint.settings, "CLIP_MODEL", "un-autre-clip")
    assert fingerprint.visual_classification_fingerprint(PAGE, LABELS) != base


def test_visual_and_textual_fingerprints_never_collide() -> None:
    assert fingerprint.visual_classification_fingerprint(PAGE, LABELS) != fingerprint.classification_fingerprint(
        PAGE, LABELS, "p"
    )
