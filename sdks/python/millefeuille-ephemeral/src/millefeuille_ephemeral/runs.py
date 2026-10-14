from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from millefeuille._files import FileInput, prepare_files
from millefeuille._polling import poll_until

from millefeuille_ephemeral._ttl import translate_ttl_errors, validate_ttl_hours
from millefeuille_ephemeral.models import EphemeralRun, EphemeralRunCreated, EphemeralRunSummary

if TYPE_CHECKING:
    from millefeuille._http import HTTPClient


class EphemeralRunsResource:
    """Ressource `/api/ephemeral/runs`. Un run démarre immédiatement à sa création (pas de `launch`)."""

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    def create(
        self,
        analyse_id: uuid.UUID | str,
        files: Iterable[FileInput],
        persist: bool = False,
        ttl_hours: int | None = None,
    ) -> EphemeralRun:
        """Flux B : crée et lance un run en un appel. `analyse_id` peut être une analyse classique."""
        ttl = validate_ttl_hours(ttl_hours)
        with translate_ttl_errors():
            response = self._http.request(
                "POST",
                "/ephemeral/runs",
                params={"ttl_hours": ttl},
                data={"analyse_id": str(analyse_id), "persist": persist},
                files=prepare_files(files),
            )
        return self.get(EphemeralRunCreated.model_validate(response.json()).run_id)

    def create_for_analyse(
        self,
        analyse_id: uuid.UUID | str,
        files: Iterable[FileInput],
        persist: bool = False,
        ttl_hours: int | None = None,
    ) -> EphemeralRun:
        """Flux A : lance un run sur une analyse déjà créée."""
        ttl = validate_ttl_hours(ttl_hours)
        with translate_ttl_errors():
            response = self._http.request(
                "POST",
                f"/ephemeral/analyses/{analyse_id}/runs",
                params={"ttl_hours": ttl},
                data={"persist": persist},
                files=prepare_files(files),
            )
        return self.get(EphemeralRunCreated.model_validate(response.json()).run_id)

    def list(self) -> Sequence[EphemeralRunSummary]:
        """Les runs de l'appelant (en cours, conservés, ou résultats conservés), du plus récent au plus ancien, 100
        au plus. Le détail d'un run se lit avec `get` ; celui d'une classification ou d'une extraction avec leur
        ressource."""
        return [EphemeralRunSummary.model_validate(item) for item in self._http.get_json("/ephemeral/runs")]

    def get(self, run_id: uuid.UUID | str) -> EphemeralRun:
        """Statut, puis résultats une fois terminé."""
        return EphemeralRun.model_validate(self._http.get_json(f"/ephemeral/runs/{run_id}"))

    def stop(self, run_id: uuid.UUID | str) -> EphemeralRun:
        """Arrête un run en cours (sans effet s'il est déjà terminé). Il reste consultable."""
        return EphemeralRun.model_validate(self._http.request("POST", f"/ephemeral/runs/{run_id}/stop").json())

    def delete(self, run_id: uuid.UUID | str) -> None:
        """Arrête si besoin puis supprime immédiatement le run, ses documents et ses résultats."""
        self._http.request("DELETE", f"/ephemeral/runs/{run_id}")

    def wait(self, run_id: uuid.UUID | str, timeout: float | None = None, poll_interval: float = 2) -> EphemeralRun:
        """Attend un statut terminal (`terminé`, `échec`, `arrêté`). `timeout=None` : sans limite."""
        return poll_until(
            lambda: self.get(run_id),
            lambda run: run.status.is_terminal,
            timeout=timeout,
            poll_interval=poll_interval,
            what=f"la fin du run {run_id}",
        )
