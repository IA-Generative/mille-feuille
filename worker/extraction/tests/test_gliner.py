"""Tests de l'extraction GLiNER : tâche, module gliner et empreinte."""

import pytest
from test_tasks import _stub_extraction, _UnitBackend

from app import fingerprint, gliner
from app.config import settings
from app.tasks import extraction as extraction_mod
from app.tasks.extraction import extract_dossier_entities

DEFS = [
    {"id": "entity-nom", "name": "nom", "definition": "Nom de famille", "type": "texte"},
    {"id": "entity-ok", "name": "complet", "definition": "Dossier complet ?", "type": "booléen"},
    {"id": "entity-vide", "name": "ville", "definition": "  ", "type": "texte"},
]


@pytest.fixture
def gliner_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Active GLiNER avec un modèle simulé ; renvoie les appels reçus (texte et définitions)."""
    monkeypatch.setattr(settings, "GLINER_ENABLED", True)
    calls: list[dict] = []

    def extract(text, entity_definitions):
        calls.append({"text": text, "names": [e["name"] for e in entity_definitions]})
        if "Dupont" in text:
            return [("nom", "Dupont", 0.9)]
        return [("nom", "DUPONT", 0.97)] if "Adresse" in text else []

    monkeypatch.setattr(extraction_mod.gliner, "extract", extract)
    return calls


def test_gliner_entities_are_deposited_with_the_gliner_source_and_merged_across_pages(
    monkeypatch, gliner_calls
) -> None:
    backend = _UnitBackend()
    backend.install(monkeypatch)
    _stub_extraction(monkeypatch)

    extract_dossier_entities.run("dossier-1")

    # Page 1 « Dupont » et page 2 « DUPONT » (casse ignorée) : une seule entité GLiNER sur les deux pages.
    gliner_predictions = [p for p in backend.predictions if p["source"] == "gliner"]
    assert len(gliner_predictions) == 1
    prediction = gliner_predictions[0]
    assert (prediction["kind"], prediction["name"], prediction["value"]) == ("entity", "nom", "Dupont")
    assert prediction["confidence"] == 0.97  # la meilleure des deux
    assert prediction["entity_definition_id"] == "entity-nom"
    assert prediction["page_ids"] == ["page-1", "page-2"]
    # Les entités du LLM restent textuelles.
    assert {p["source"] for p in backend.predictions if p["source"] != "gliner"} == {"textual"}


def test_gliner_runs_in_its_own_unit_per_document(monkeypatch, gliner_calls) -> None:
    backend = _UnitBackend()
    backend.install(monkeypatch)
    _stub_extraction(monkeypatch)

    extract_dossier_entities.run("dossier-1")

    gliner_units = [u for u in backend.declared if u["description"].get("source") == "gliner"]
    assert [u["description"]["document_id"] for u in gliner_units] == ["doc-1"]
    assert gliner_units[0]["kind"] == "extraction"
    assert [p["unit_id"] for p in backend.predictions if p["source"] == "gliner"] == ["unit-2"]
    assert len(gliner_calls) == 2  # une fois par page


def test_a_failing_gliner_never_fails_the_llm_extraction(monkeypatch, gliner_calls) -> None:
    backend = _UnitBackend()
    backend.install(monkeypatch)
    _stub_extraction(monkeypatch)

    def broken(text, entity_definitions):
        raise RuntimeError("modèle indisponible")

    monkeypatch.setattr(extraction_mod.gliner, "extract", broken)

    extract_dossier_entities.run("dossier-1")  # ne lève pas

    assert {p["source"] for p in backend.predictions} == {"textual"}
    assert ("unit-2", "échec") in backend.completed


def test_nothing_gliner_happens_when_disabled(monkeypatch) -> None:
    backend = _UnitBackend()
    backend.install(monkeypatch)
    _stub_extraction(monkeypatch)

    extract_dossier_entities.run("dossier-1")

    assert all(u["description"].get("source") != "gliner" for u in backend.declared)
    assert {p["source"] for p in backend.predictions} == {"textual"}


def test_a_reused_gliner_unit_is_not_computed(monkeypatch, gliner_calls) -> None:
    first = _UnitBackend()
    first.install(monkeypatch)
    _stub_extraction(monkeypatch)
    extract_dossier_entities.run("dossier-1")
    fingerprints = [u["input_fingerprint"] for u in first.declared]
    gliner_calls.clear()

    again = _UnitBackend()
    again.reuse = {fp: [] for fp in fingerprints}
    again.install(monkeypatch)
    extract_dossier_entities.run("dossier-1")

    assert gliner_calls == []
    assert again.predictions == []


def test_only_definitions_gliner_can_extract_are_sent(monkeypatch, gliner_calls) -> None:
    backend = _UnitBackend()
    backend.install(monkeypatch)
    _stub_extraction(monkeypatch)
    monkeypatch.setattr(
        extraction_mod.api_client,
        "get_analyse_definitions",
        lambda client, analyse_id: {"extraction": {"prompt": "p", "entities": DEFS}},
    )

    extract_dossier_entities.run("dossier-1")

    assert gliner_calls and all(call["names"] == ["nom", "ville"] for call in gliner_calls)


# --- Module gliner (modèle simulé : le vrai n'est jamais chargé) ---


class _FakeModel:
    def __init__(self, entities: dict) -> None:
        self.entities = entities
        self.calls: list[dict] = []

    def extract_entities_long(self, text, entity_types, **kwargs):
        self.calls.append({"text": text, "entity_types": entity_types, **kwargs})
        return {"entities": self.entities}


def test_definitions_become_the_descriptions_given_to_gliner(monkeypatch) -> None:
    model = _FakeModel({})
    monkeypatch.setattr(gliner, "_load", lambda: model)
    gliner.extract("du texte", DEFS)
    assert model.calls[0]["entity_types"] == {"nom": "Nom de famille", "complet": "Dossier complet ?", "ville": "ville"}
    assert model.calls[0]["include_confidence"] is True
    assert model.calls[0]["threshold"] == settings.GLINER_THRESHOLD


def test_extract_returns_name_value_and_confidence_and_drops_unknown_names(monkeypatch) -> None:
    model = _FakeModel(
        {
            "nom": [{"text": " Dupont ", "confidence": 0.9}, {"text": "  ", "confidence": 0.99}],
            "inconnue": [{"text": "x", "confidence": 0.9}],
        }
    )
    monkeypatch.setattr(gliner, "_load", lambda: model)
    assert gliner.extract("Dupont", DEFS) == [("nom", "Dupont", 0.9)]


def test_extract_without_text_or_definitions_never_loads_the_model(monkeypatch) -> None:
    def boom():
        raise AssertionError("le modèle ne doit pas être chargé")

    monkeypatch.setattr(gliner, "_load", boom)
    assert gliner.extract("   ", DEFS) == []
    assert gliner.extract("texte", []) == []


def test_supported_drops_boolean_definitions() -> None:
    assert [e["name"] for e in gliner.supported(DEFS)] == ["nom", "ville"]


# --- Empreinte ---


PAGES = [{"page_number": 1, "content": "Nom: Dupont"}, {"page_number": 2, "content": "Adresse"}]


def test_gliner_fingerprint_depends_on_text_definitions_model_and_threshold(monkeypatch) -> None:
    base = fingerprint.gliner_extraction_fingerprint(PAGES, DEFS)
    assert base == fingerprint.gliner_extraction_fingerprint([dict(p) for p in PAGES], [dict(d) for d in DEFS])
    variants = {
        fingerprint.gliner_extraction_fingerprint([{**PAGES[0], "content": "Nom: Durand"}, PAGES[1]], DEFS),
        fingerprint.gliner_extraction_fingerprint(PAGES, DEFS[:1]),
        fingerprint.gliner_extraction_fingerprint(PAGES[:1], DEFS),
    }
    assert base not in variants and len(variants) == 3
    monkeypatch.setattr(fingerprint.settings, "GLINER_MODEL", "un-autre-modele")
    assert fingerprint.gliner_extraction_fingerprint(PAGES, DEFS) != base
    monkeypatch.undo()
    monkeypatch.setattr(fingerprint.settings, "GLINER_THRESHOLD", 0.9)
    assert fingerprint.gliner_extraction_fingerprint(PAGES, DEFS) != base


def test_gliner_and_llm_fingerprints_never_collide() -> None:
    assert fingerprint.gliner_extraction_fingerprint(PAGES, DEFS) != fingerprint.extraction_fingerprint(
        PAGES, DEFS, "p"
    )
