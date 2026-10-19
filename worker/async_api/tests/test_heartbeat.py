"""Le pont annonce-t-il qu'il consomme, avec le nom du manifeste et la version de l'image ?"""

import json
from pathlib import Path

import pytest
from mic_worker.typed import HEARTBEAT_API_KEY_HEADER

from src.heartbeat import VERSION_INCONNUE, build_heartbeat_config, version_de_l_image

_URL = "http://async-api-apisix.async-api.svc.cluster.local"
_SERVICE = "mille-feuille"


@pytest.fixture
def version_json(tmp_path: Path) -> Path:
    chemin = tmp_path / "version.json"
    chemin.write_text(json.dumps({"version": "0.27.0", "commit": "abc1234"}), encoding="utf-8")
    return chemin


def test_build_heartbeat_config_without_api_url_disables_the_heartbeat(version_json: Path) -> None:
    config = build_heartbeat_config(_SERVICE, environ={}, chemin_version=version_json)

    assert config is None


def test_build_heartbeat_config_takes_the_service_from_the_manifest_and_the_version_from_the_image(
    version_json: Path,
) -> None:
    # Arrange
    environ = {"HEARTBEAT_API_URL": _URL, "HEARTBEAT_API_KEY": "cle-de-test"}

    # Act
    config = build_heartbeat_config(_SERVICE, environ=environ, chemin_version=version_json)

    # Assert
    assert config is not None
    assert config.api_url == _URL
    assert config.service == _SERVICE
    assert config.version == "0.27.0"
    assert config.api_key == "cle-de-test"
    assert config.api_key_header == HEARTBEAT_API_KEY_HEADER


def test_build_heartbeat_config_lets_the_environment_override_service_and_version(version_json: Path) -> None:
    environ = {"HEARTBEAT_API_URL": _URL, "HEARTBEAT_SERVICE": "autre", "HEARTBEAT_VERSION": "9.9.9"}

    config = build_heartbeat_config(_SERVICE, environ=environ, chemin_version=version_json)

    assert config is not None
    assert (config.service, config.version) == ("autre", "9.9.9")


def test_build_heartbeat_config_without_version_file_reports_dev(tmp_path: Path) -> None:
    environ = {"HEARTBEAT_API_URL": _URL}

    config = build_heartbeat_config(_SERVICE, environ=environ, chemin_version=tmp_path / "absent.json")

    assert config is not None
    assert config.version == VERSION_INCONNUE


def test_version_de_l_image_with_unreadable_json_is_dev(tmp_path: Path) -> None:
    chemin = tmp_path / "version.json"
    chemin.write_text("{", encoding="utf-8")

    assert version_de_l_image(chemin) == VERSION_INCONNUE
