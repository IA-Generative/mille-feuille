"""Tests pour summarize_text et les tâches de résumé (issue #52)."""

from unittest.mock import MagicMock, patch

from app.llm import summarize_text


def test_summarize_text_returns_empty_for_empty_input() -> None:
    assert summarize_text("") == ""
    assert summarize_text("   ") == ""


def test_summarize_text_calls_llm_and_returns_content() -> None:
    fake_response = MagicMock()
    fake_response.choices = [MagicMock()]
    fake_response.choices[0].message.content = "Voici un résumé concis."

    with patch("app.llm._client") as mock_client:
        mock_client.return_value.chat.completions.create.return_value = fake_response
        result = summarize_text("Un long texte à résumer.")

    assert result == "Voici un résumé concis."
    mock_client.return_value.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.return_value.chat.completions.create.call_args
    assert call_kwargs.kwargs["temperature"] == 0.1
    assert call_kwargs.kwargs["max_tokens"] == 500
    messages = call_kwargs.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "synthèse" in messages[0]["content"].lower()
    assert messages[1]["content"] == "Un long texte à résumer."


def test_summarize_text_truncates_long_content() -> None:
    """Le contenu très long est tronqué par l'appelant (tâche), pas par
    summarize_text elle-même — mais on vérifie que max_tokens est respecté."""
    fake_response = MagicMock()
    fake_response.choices = [MagicMock()]
    fake_response.choices[0].message.content = "Résumé court."

    long_text = "x" * 50_000
    with patch("app.llm._client") as mock_client:
        mock_client.return_value.chat.completions.create.return_value = fake_response
        summarize_text(long_text, max_tokens=200)

    call_kwargs = mock_client.return_value.chat.completions.create.call_args
    assert call_kwargs.kwargs["max_tokens"] == 200


def test_source_header_gives_the_source_of_the_document_in_context() -> None:
    from app.tasks.summary import _source_header

    assert _source_header({"name": "a.pdf"}) == ""
    assert _source_header({"source": {"name": "Guichet", "description": "En main propre"}}) == (
        "Source du document : Guichet — En main propre\n\n"
    )
    assert _source_header({"source": {"name": "Guichet", "description": ""}}) == "Source du document : Guichet\n\n"
