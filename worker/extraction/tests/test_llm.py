"""Tests des modèles de structured output de l'extraction."""

import pytest

from app.llm import EntityValue, ExtractionResult


def test_entity_value_model() -> None:
    entity = EntityValue(
        entity_name="montant_total",
        value="42.50 €",
        confidence=0.9,
        page_numbers=[1, 2],
    )
    assert entity.entity_name == "montant_total"
    assert entity.value == "42.50 €"
    assert entity.confidence == 0.9
    assert entity.page_numbers == [1, 2]


def test_extraction_result_model() -> None:
    entities = [
        EntityValue(entity_name="nom", value="Dupont", confidence=0.95, page_numbers=[1]),
        EntityValue(entity_name="date", value="2024-01-15", confidence=0.88, page_numbers=[1]),
    ]
    result = ExtractionResult(entities=entities)
    assert len(result.entities) == 2
    assert result.entities[0].entity_name == "nom"
    assert result.entities[1].entity_name == "date"


def test_extraction_result_empty() -> None:
    result = ExtractionResult()
    assert result.entities == []


def test_client_applies_the_hub_timeout_and_retries_of_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import llm

    monkeypatch.setattr(llm.settings, "OPENAI_API_KEY", "cle-de-test")
    monkeypatch.setattr(llm.settings, "OPENAI_API_BASE_URL", "http://hub.test/v1")
    monkeypatch.setattr(llm.settings, "OPENAI_TIMEOUT_SECONDS", 7.5)
    monkeypatch.setattr(llm.settings, "OPENAI_MAX_RETRIES", 1)

    client = llm._client()

    assert client.timeout == 7.5
    assert client.max_retries == 1
