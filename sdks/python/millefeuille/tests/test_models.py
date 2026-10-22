"""Validation des entrées et typage strict des sorties."""

from __future__ import annotations

import httpx
import pytest
from conftest import analyse_json, dossier_json
from pydantic import ValidationError as PydanticValidationError

from millefeuille import models as m


def test_inputs_reject_blank_and_unknown_fields() -> None:
    with pytest.raises(PydanticValidationError):
        m.AnalyseCreate(name="n", description="")
    with pytest.raises(PydanticValidationError):
        m.AnalyseCreate(name="n", description="   ")
    with pytest.raises(PydanticValidationError):
        m.AnalyseCreate(name="n", description="d", nom="typo")  # type: ignore[call-arg]
    with pytest.raises(PydanticValidationError):
        m.AgentCreate(name="a", prompt="  ")
    with pytest.raises(PydanticValidationError):
        m.EntityDefinitionIn(name="e", type="couleur")  # type: ignore[arg-type]
    with pytest.raises(PydanticValidationError):
        m.AgentCreate(name="a", prompt="p", tools="calculatrice")  # type: ignore[arg-type]
    with pytest.raises(PydanticValidationError):
        m.DossierCreate(name="d", analyse_id="pas-un-uuid")  # type: ignore[arg-type]


def test_any_tool_identifier_is_accepted_the_server_validates_it() -> None:
    """Un outil d'agent est un identifiant (interne ou d'un serveur MCP) : le SDK ne peut pas connaître la liste."""
    agent = m.AgentCreate(name="a", prompt="p", tools=["calculatrice", "calcul_dates", "0b6f3c2a-9d1e-4f5a-8c7b-1"])
    assert agent.tools == ["calculatrice", "calcul_dates", "0b6f3c2a-9d1e-4f5a-8c7b-1"]


def test_invalid_input_never_reaches_the_network(make_client) -> None:
    client, seen = make_client(lambda r: httpx.Response(500))
    with pytest.raises(PydanticValidationError):
        client.analyses.create("n", "")
    with pytest.raises(PydanticValidationError):
        client.dossiers.create("d", analyse_id="pas-un-uuid")
    assert seen == []


def test_outputs_are_fully_typed() -> None:
    dossier = m.Dossier.model_validate(dossier_json())
    assert isinstance(dossier.status, m.DossierStatus)
    step = dossier.execution_steps[0]
    assert isinstance(step.kind, m.ExecutionStepKind) and isinstance(step.logs[0].level, m.ExecutionLogLevel)
    page = dossier.documents[0].pages[0]
    assert isinstance(page.predictions[0].kind, m.PredictionKind)
    assert isinstance(page.predictions[0].validations[0].status, m.PredictionValidationStatus)
    analyse = m.Analyse.model_validate(analyse_json())
    assert isinstance(analyse.extraction.entities[0].type, m.EntityType)
    assert isinstance(analyse.agents[0].tools[0], str)


def test_unexpected_enum_value_from_server_is_rejected() -> None:
    payload = dossier_json()
    payload["execution_steps"][0]["status"] = "inconnu"
    with pytest.raises(PydanticValidationError):
        m.Dossier.model_validate(payload)


def test_missing_required_field_is_rejected() -> None:
    payload = dossier_json()
    del payload["analyse_version"]
    with pytest.raises(PydanticValidationError):
        m.Dossier.model_validate(payload)


def test_unknown_response_fields_are_ignored() -> None:
    payload = dossier_json()
    payload["champ_futur"] = 1
    assert not hasattr(m.Dossier.model_validate(payload), "champ_futur")
