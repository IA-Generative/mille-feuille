"""Tests des modèles de structured output de l'extraction."""

from types import SimpleNamespace

import pytest
from openai import LengthFinishReasonError
from openai.types.chat import ChatCompletion

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


# --- Sortie structurée bornée, avec repli ---------------------------------------------------------


class _Message:
    def __init__(self, parsed=None, content=None):
        self.parsed = parsed
        self.content = content


class _Reponse:
    def __init__(self, parsed=None, content=None, finish_reason="stop"):
        self.choices = [SimpleNamespace(message=_Message(parsed, content), finish_reason=finish_reason)]


def _erreur_de_longueur() -> LengthFinishReasonError:
    completion = ChatCompletion.model_construct(
        id="x", choices=[], created=0, model="chat", object="chat.completion", usage=None
    )
    return LengthFinishReasonError(completion=completion)


class _ClientFactice:
    """Un client OpenAI réduit à ce que _completion_structuree appelle ; enregistre les arguments reçus."""

    def __init__(self, *, parse=None, create=None):
        self.appels_parse: list[dict] = []
        self.appels_create: list[dict] = []
        self._parse = parse
        self._create = create
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=self._faire_parse)))
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._faire_create))

    def _faire_parse(self, **kwargs):
        self.appels_parse.append(kwargs)
        if isinstance(self._parse, Exception):
            raise self._parse
        return self._parse

    def _faire_create(self, **kwargs):
        self.appels_create.append(kwargs)
        return self._create


@pytest.fixture
def client_factice(monkeypatch: pytest.MonkeyPatch):
    from app import llm

    def _installer(**kwargs) -> _ClientFactice:
        client = _ClientFactice(**kwargs)
        monkeypatch.setattr(llm, "_client", lambda: client)
        return client

    return _installer


def _extraire():
    from app.llm import extract_entities_batch

    return extract_entities_batch(
        pages=[{"page_number": 1, "content": "Accord entre la France et la Russie"}],
        entity_definitions=[{"name": "pays", "type": "texte", "definition": "Pays cité"}],
        extraction_prompt="Extrais les pays.",
    )


def test_extract_entities_batch_bounds_the_answer_with_the_reserved_output_tokens(client_factice, monkeypatch) -> None:
    from app import llm

    monkeypatch.setattr(llm.settings, "EXTRACTION_RESERVED_OUTPUT_TOKENS", 321)
    attendu = ExtractionResult(entities=[EntityValue(entity_name="pays", value="France", confidence=0.9)])
    client = client_factice(parse=_Reponse(parsed=attendu))

    resultat = _extraire()

    assert resultat is attendu
    assert client.appels_parse[0]["max_tokens"] == 321
    assert client.appels_create == []


def test_extract_entities_batch_falls_back_to_json_object_when_the_structured_answer_is_truncated(
    client_factice,
) -> None:
    client = client_factice(
        parse=_erreur_de_longueur(),
        create=_Reponse(
            content='{"entities": [{"entity_name": "pays", "value": "Russie", "confidence": 0.8, "page_numbers": [1]}]}'
        ),
    )

    resultat = _extraire()

    assert [e.value for e in resultat.entities] == ["Russie"]
    appel = client.appels_create[0]
    assert appel["response_format"] == {"type": "json_object"}
    assert "entity_name" in appel["messages"][0]["content"]


def test_extract_entities_batch_fails_when_the_fallback_answer_does_not_match_the_schema(client_factice) -> None:
    from pydantic import ValidationError

    client_factice(parse=_erreur_de_longueur(), create=_Reponse(content='{"entities": [{"value": "France"}]}'))

    with pytest.raises(ValidationError):
        _extraire()
