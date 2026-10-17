"""Tests pour les modèles de structured output et le client LLM."""

from unittest.mock import MagicMock, patch

import pytest

from app.llm import (
    AnalyseSuggestion,
    SuggestionResult,
    suggest_analyses,
)


def test_suggestion_result_model() -> None:
    suggestions = [
        AnalyseSuggestion(analyse_id="a-1", score=0.92, rationale="Correspondance forte"),
        AnalyseSuggestion(analyse_id="a-2", score=0.45, rationale="Moins pertinent"),
    ]
    result = SuggestionResult(suggestions=suggestions)
    assert len(result.suggestions) == 2
    assert result.suggestions[0].analyse_id == "a-1"
    assert result.suggestions[0].score == 0.92
    assert result.suggestions[1].rationale == "Moins pertinent"


def test_suggest_analyses_calls_llm_with_structured_output() -> None:
    """suggest_analyses utilise beta.chat.completions.parse avec
    response_format=SuggestionResult."""
    fake_parsed = SuggestionResult(
        suggestions=[
            AnalyseSuggestion(analyse_id="a-1", score=0.9, rationale="OK"),
        ]
    )
    fake_response = MagicMock()
    fake_response.choices = [MagicMock()]
    fake_response.choices[0].message.parsed = fake_parsed

    with patch("app.llm._client") as mock_client:
        mock_client.return_value.beta.chat.completions.parse.return_value = fake_response
        result = suggest_analyses(
            dossier_summary="Dossier avec CNI",
            analyses=[{"id": "a-1", "name": "Analyse CNI"}],
        )

    assert len(result.suggestions) == 1
    assert result.suggestions[0].analyse_id == "a-1"
    call_kwargs = mock_client.return_value.beta.chat.completions.parse.call_args
    assert call_kwargs.kwargs["response_format"] == SuggestionResult
    messages = call_kwargs.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "CNI" in messages[1]["content"]


def test_client_applies_the_hub_timeout_and_retries_of_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import llm

    monkeypatch.setattr(llm.settings, "OPENAI_API_KEY", "cle-de-test")
    monkeypatch.setattr(llm.settings, "OPENAI_API_BASE_URL", "http://hub.test/v1")
    monkeypatch.setattr(llm.settings, "OPENAI_TIMEOUT_SECONDS", 7.5)
    monkeypatch.setattr(llm.settings, "OPENAI_MAX_RETRIES", 1)

    client = llm._client()

    assert client.timeout == 7.5
    assert client.max_retries == 1
