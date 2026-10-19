"""Heartbeat vers async-api : le pont annonce qu'il consomme (mic-worker, PR async-api #668).

Activé par le déploiement seul (`HEARTBEAT_API_URL`, le Service interne de la passerelle APISIX
d'async-api, jamais l'adresse publique). Le nom du service vient du manifeste et la version de
l'image (`/app/version.json`) quand l'environnement ne les donne pas : une release n'a rien à
réécrire. La clé (`HEARTBEAT_API_KEY`) est celle d'un consommateur autorisé sur le service ; sans
elle la passerelle refuse le battement, mic-worker le journalise et continue de consommer.
"""

import json
import os
from collections.abc import Mapping
from pathlib import Path

from mic_worker.health import CHEMIN_VERSION_JSON
from mic_worker.typed import ENV_SERVICE, ENV_VERSION, HeartbeatConfig

VERSION_INCONNUE = "dev"
_CLE_VERSION = "version"


def version_de_l_image(chemin: Path = CHEMIN_VERSION_JSON) -> str:
    """Version écrite par le build dans `version.json` ; `dev` hors image ou fichier illisible."""
    try:
        version = json.loads(chemin.read_text(encoding="utf-8")).get(_CLE_VERSION)
    except (OSError, ValueError, AttributeError):
        return VERSION_INCONNUE
    return str(version) if version else VERSION_INCONNUE


def build_heartbeat_config(
    service: str,
    environ: Mapping[str, str] | None = None,
    chemin_version: Path = CHEMIN_VERSION_JSON,
) -> HeartbeatConfig | None:
    """`None` tant que `HEARTBEAT_API_URL` est absente ; sinon la configuration de mic-worker,
    complétée par le nom du service et la version de l'image si l'environnement ne les fixe pas."""
    env = dict(os.environ if environ is None else environ)
    if not env.get(ENV_SERVICE):
        env[ENV_SERVICE] = service
    if not env.get(ENV_VERSION):
        env[ENV_VERSION] = version_de_l_image(chemin_version)
    return HeartbeatConfig.from_env(env)
