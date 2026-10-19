"""Tests des modèles de structured output de la classification."""

from types import SimpleNamespace

import pytest
from openai import LengthFinishReasonError
from openai.types.chat import ChatCompletion

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


def _classer(**surcharges):
    from app.llm import classify_page

    arguments = dict(
        page_text="Décret portant publication de l'accord entre la France et la Russie",
        image_description="Page de journal officiel",
        label_definitions=[
            {"name": "accord", "definition": "Accord international"},
            {"name": "autre", "definition": "Autre"},
        ],
        classification_prompt="Classe chaque page.",
    )
    arguments.update(surcharges)
    return classify_page(**arguments)


def test_classify_page_bounds_the_answer_and_returns_the_parsed_result(client_factice, monkeypatch) -> None:
    from app import llm

    monkeypatch.setattr(llm.settings, "LLM_MAX_OUTPUT_TOKENS", 123)
    attendu = ClassificationResult(prediction=LabelPrediction(label_name="accord", confidence=0.9))
    client = client_factice(parse=_Reponse(parsed=attendu))

    resultat = _classer()

    assert resultat is attendu
    assert client.appels_parse[0]["max_tokens"] == 123
    assert client.appels_parse[0]["response_format"] is ClassificationResult
    assert client.appels_create == []


def test_classify_page_falls_back_to_json_object_when_the_structured_answer_is_truncated(client_factice) -> None:
    client = client_factice(
        parse=_erreur_de_longueur(),
        create=_Reponse(content='{"prediction": {"label_name": "accord", "confidence": 1.0, "reasoning": "accord"}}'),
    )

    resultat = _classer()

    assert resultat.prediction.label_name == "accord"
    appel = client.appels_create[0]
    assert appel["response_format"] == {"type": "json_object"}
    assert appel["max_tokens"] == client.appels_parse[0]["max_tokens"]
    assert appel["messages"][0]["role"] == "system"
    assert "label_name" in appel["messages"][0]["content"]  # le schéma est décrit dans la consigne
    assert len(appel["messages"]) == 2


def test_classify_page_falls_back_when_the_structured_answer_is_empty(client_factice) -> None:
    client = client_factice(
        parse=_Reponse(parsed=None, finish_reason="length"),
        create=_Reponse(content='{"prediction": {"label_name": "autre", "confidence": 0.5}}'),
    )

    resultat = _classer()

    assert resultat.prediction.label_name == "autre"
    assert len(client.appels_create) == 1


def test_classify_page_fails_when_the_fallback_answer_does_not_match_the_schema(client_factice) -> None:
    from pydantic import ValidationError

    client_factice(parse=_erreur_de_longueur(), create=_Reponse(content='{"label": "accord"}'))

    with pytest.raises(ValidationError):
        _classer()


def test_classify_page_multi_label_uses_the_multi_label_schema(client_factice) -> None:
    attendu = MultiLabelClassificationResult(predictions=[LabelPrediction(label_name="accord", confidence=0.8)])
    client = client_factice(parse=_Reponse(parsed=attendu))

    resultat = _classer(multi_label=True)

    assert resultat is attendu
    assert client.appels_parse[0]["response_format"] is MultiLabelClassificationResult
