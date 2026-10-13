"""Tests de l'empreinte d'une unité de classification."""

from app import fingerprint

PAGE = {"content": "Carte d'identité", "screenshot_key": "screens/p1.png"}
LABELS = [{"id": "l1", "name": "CNI", "definition": "Carte nationale d'identité"}]


def test_classification_fingerprint_multi_label_changes_only_multi_label_analyses() -> None:
    mono = fingerprint.classification_fingerprint(PAGE, LABELS, "Classe.")
    assert mono == fingerprint.classification_fingerprint(PAGE, LABELS, "Classe.", multi_label=False)
    assert fingerprint.classification_fingerprint(PAGE, LABELS, "Classe.", multi_label=True) != mono


def test_classification_fingerprint_depends_on_text_screenshot_labels_prompt_and_models(monkeypatch) -> None:
    base = fingerprint.classification_fingerprint(PAGE, LABELS, "Classe.")
    assert base == fingerprint.classification_fingerprint(dict(PAGE), [dict(LABELS[0])], "Classe.")
    variants = {
        fingerprint.classification_fingerprint({**PAGE, "content": "Passeport"}, LABELS, "Classe."),
        fingerprint.classification_fingerprint({**PAGE, "screenshot_key": "screens/p2.png"}, LABELS, "Classe."),
        fingerprint.classification_fingerprint(PAGE, [{**LABELS[0], "name": "Passeport"}], "Classe."),
        fingerprint.classification_fingerprint(PAGE, LABELS, "Classe autrement."),
    }
    assert base not in variants and len(variants) == 4
    monkeypatch.setattr(fingerprint.settings, "VLM_MODEL", "un-autre-vlm")
    assert fingerprint.classification_fingerprint(PAGE, LABELS, "Classe.") != base
