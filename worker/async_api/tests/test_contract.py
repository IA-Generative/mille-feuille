"""Le manifeste `contrat.json` et les modèles d'entrée disent-ils la même chose, et ce que la plateforme attend ?"""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft7Validator
from mic_worker.manifeste import charger
from millefeuille_ephemeral import EphemeralAnalysisConfig
from pydantic import ValidationError

from src.config import TTL_MAX_PLATEFORME, settings
from src.enums import OutilAgent
from src.messages import AgentDefinition, AnalysisDefinition, AnalyzeRequest, FileRef

CONTRAT = Path(__file__).resolve().parents[1] / "contrat.json"
_OCTETS_PAR_MIO = 1024 * 1024


def _charge() -> dict[str, Any]:
    return json.loads(CONTRAT.read_text(encoding="utf-8"))


def _entree() -> dict[str, Any]:
    return _charge()["entree"]


def _sous_schemas_avec_exemples(schema: dict[str, Any], chemin: str = "") -> list[tuple[str, dict[str, Any]]]:
    """Chaque sous-schéma qui porte `examples`, avec son chemin, en profondeur (propriétés et tableaux)."""
    trouves = [(chemin or "<racine>", schema)] if "examples" in schema else []
    for nom, sous in (schema.get("properties") or {}).items():
        trouves.extend(_sous_schemas_avec_exemples(sous, f"{chemin}.{nom}" if chemin else nom))
    if isinstance(schema.get("items"), dict):
        trouves.extend(_sous_schemas_avec_exemples(schema["items"], f"{chemin}[]"))
    return trouves


def test_manifest_is_valid_for_mic_worker() -> None:
    # Act
    manifeste = charger(CONTRAT)

    # Assert
    assert manifeste.nom == "mille-feuille"
    assert manifeste.classe.value == "long"
    assert manifeste.gpu is False
    assert manifeste.moteur and "mille-feuille" in manifeste.moteur


def test_manifest_file_size_bound_equals_the_worker_bound() -> None:
    # Arrange
    manifeste = charger(CONTRAT)

    # Assert : une seule borne, déclarée une fois — l'API refuse en 413 ce que le worker refuserait après coup.
    assert manifeste.taille_max_fichier_mio == settings.MAX_FILE_SIZE_BYTES // _OCTETS_PAR_MIO


def test_input_schema_is_a_valid_draft7_schema() -> None:
    # Act / Assert
    Draft7Validator.check_schema(_entree())


def test_input_schema_matches_the_request_model() -> None:
    # Arrange
    schema = _entree()

    # Assert
    assert set(schema["properties"]) == set(AnalyzeRequest.model_fields)
    assert set(schema["required"]) == {"files"}
    assert schema["properties"]["files"]["maxItems"] == settings.MAX_FILES
    assert set(schema["properties"]["files"]["items"]["properties"]) == set(FileRef.model_fields)
    assert schema["properties"]["ttl_hours"]["maximum"] == TTL_MAX_PLATEFORME


def test_analysis_schema_matches_the_platform_model() -> None:
    # Arrange
    analysis = _entree()["properties"]["analysis"]

    # Assert
    assert set(analysis["properties"]) == set(AnalysisDefinition.model_fields)
    assert set(analysis["properties"]["agents"]["items"]["properties"]) == set(AgentDefinition.model_fields)


def test_platform_model_mirrors_the_sdk_config_without_persist() -> None:
    # Assert : si le SDK gagne un champ, ce test le dit ; `persist` est le seul écart voulu.
    assert set(AnalysisDefinition.model_fields) == set(EphemeralAnalysisConfig.model_fields) - {"persist"}


def test_agent_tools_enum_is_the_platform_enum() -> None:
    # Arrange
    outils = _entree()["properties"]["analysis"]["properties"]["agents"]["items"]["properties"]["tools"]["items"]

    # Assert
    assert outils["enum"] == [outil.value for outil in OutilAgent]
    assert "recherche_web" not in outils["enum"]


@pytest.mark.parametrize(
    ("chemin", "schema"), _sous_schemas_avec_exemples(_entree()), ids=lambda x: x if isinstance(x, str) else ""
)
def test_every_example_validates_against_its_schema(chemin: str, schema: dict[str, Any]) -> None:
    # Act / Assert : le premier exemple de chaque sous-schéma est conforme à ce sous-schéma.
    assert schema["examples"], chemin
    Draft7Validator(schema).validate(schema["examples"][0])


def test_top_level_examples_are_accepted_by_the_request_model() -> None:
    # Arrange : un exemple par variante (`analysis`, `analyse_id`).
    exemples = _entree()["examples"]

    # Act
    requetes = [AnalyzeRequest.model_validate(exemple) for exemple in exemples]

    # Assert
    assert len(exemples) == 2
    assert {requete.analysis is not None for requete in requetes} == {True, False}


@pytest.mark.parametrize(
    "corps",
    [
        {"files": [{"file_id": "c/1/a.pdf"}], "analysis": {"name": "n"}, "persist": True},
        {"files": [{"file_id": "c/1/a.pdf"}], "analysis": {"name": "n", "persist": True}},
        {
            "files": [{"file_id": "c/1/a.pdf"}],
            "analysis": {"name": "n"},
            "analyse_id": "3f2b8c1e-5d4a-4e6b-9a7c-1d2e3f4a5b6c",
        },
        {"files": [{"file_id": "c/1/a.pdf"}]},
        {
            "files": [{"file_id": "c/1/a.pdf"}],
            "analysis": {"name": "n", "agents": [{"name": "a", "prompt": "p", "tools": ["recherche_web"]}]},
        },
        {"files": [{"file_id": "c/1/a.pdf"}], "analysis": {"name": "n"}, "ttl_hours": TTL_MAX_PLATEFORME + 1},
        {"files": [{"file_id": f"c/1/{i}.pdf"} for i in range(21)], "analysis": {"name": "n"}},
    ],
    ids=[
        "persist",
        "persist-dans-analysis",
        "deux-sources",
        "aucune-source",
        "outil-ferme",
        "ttl-trop-long",
        "trop-de-fichiers",
    ],
)
def test_schema_and_model_both_refuse_the_same_bodies(corps: dict[str, Any]) -> None:
    # Act
    erreurs_schema = list(Draft7Validator(_entree()).iter_errors(corps))

    # Assert : refusé par le schéma (c'est ce que l'API applique) ET par le modèle (c'est ce que le worker applique).
    assert erreurs_schema
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate(corps)


def test_vers_config_forces_persist_false_and_keeps_the_definition() -> None:
    # Arrange
    definition = AnalysisDefinition.model_validate(_entree()["properties"]["analysis"]["examples"][0])

    # Act
    config = definition.vers_config()

    # Assert
    assert config.persist is False
    assert config.name == definition.name
    assert [agent.tools for agent in config.agents] == [[OutilAgent.LECTURE_DOCUMENT]]


def test_display_name_defaults_to_last_key_segment() -> None:
    assert FileRef(file_id="astree/a1/cni.pdf").display_name == "cni.pdf"
    assert FileRef(file_id="astree/a1/cni.pdf", name="Ma CNI").display_name == "Ma CNI"
