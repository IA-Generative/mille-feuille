from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from millefeuille._files import FileInput, prepare_file
from millefeuille._polling import poll_until

from millefeuille_ephemeral._ttl import translate_ttl_errors, validate_ttl_hours
from millefeuille_ephemeral.models import EphemeralRunCreated, _OneShotRun

if TYPE_CHECKING:
    from millefeuille._http import HTTPClient


class OneShotResource[T: _OneShotRun]:
    """Base des routes « un document, un appel » : le run (analyse éphémère à une seule étape) est créé avec le
    fichier et démarre aussitôt. Même cycle de vie et même TTL que les autres runs : `client.runs.stop` et
    `client.runs.delete` s'appliquent."""

    _path: str
    _model: type[T]

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    def _create(self, file: FileInput, data: dict[str, Any], ttl_hours: int | None) -> T:
        ttl = validate_ttl_hours(ttl_hours)
        with translate_ttl_errors():
            response = self._http.request(
                "POST", self._path, params={"ttl_hours": ttl}, data=data, files=[prepare_file(file)]
            )
        return self.get(EphemeralRunCreated.model_validate(response.json()).run_id)

    def get(self, run_id: uuid.UUID | str) -> T:
        """Statut, puis résultats une fois terminé (les pages se remplissent au fil du run)."""
        return self._model.model_validate(self._http.get_json(f"{self._path}/{run_id}"))

    def wait(self, run_id: uuid.UUID | str, timeout: float | None = None, poll_interval: float = 2) -> T:
        """Attend un statut terminal (`terminé`, `échec`, `arrêté`). `timeout=None` : sans limite."""
        return poll_until(
            lambda: self.get(run_id),
            lambda result: result.status.is_terminal,
            timeout=timeout,
            poll_interval=poll_interval,
            what=f"la fin du run {run_id}",
        )
