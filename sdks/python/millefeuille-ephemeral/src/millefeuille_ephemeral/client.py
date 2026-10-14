from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterable, Sequence
from types import TracebackType

import httpx
from millefeuille._files import FileInput
from millefeuille._http import DEFAULT_TIMEOUT, HTTPClient
from millefeuille.exceptions import NotFoundError
from millefeuille.models import EntityDefinitionIn, LabelDefinitionIn

from millefeuille_ephemeral.analyses import EphemeralAnalysesResource
from millefeuille_ephemeral.classifications import EphemeralClassificationsResource
from millefeuille_ephemeral.extractions import EphemeralExtractionsResource
from millefeuille_ephemeral.models import (
    TTL_DEFAULT_HOURS,
    EphemeralAnalysisConfig,
    EphemeralClassification,
    EphemeralExtraction,
    EphemeralRun,
)
from millefeuille_ephemeral.runs import EphemeralRunsResource


class EphemeralClient:
    """Client de l'API éphémère : analyses et runs à la volée, avec TTL et purge automatique.

    Authentification (au moins une méthode) : `api_token` (`X-App-Token`, recommandé pour un
    usage programmatique), `bearer_token` (access token Keycloak) ou `session_cookie`.
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_token: str | None = None,
        bearer_token: str | None = None,
        session_cookie: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not (api_token or bearer_token or session_cookie):
            raise ValueError("Fournir api_token, bearer_token ou session_cookie.")
        self._http = HTTPClient(
            base_url=base_url,
            api_token=api_token,
            bearer_token=bearer_token,
            session_cookie=session_cookie,
            timeout=timeout,
            max_retries=max_retries,
            backoff_factor=backoff_factor,
            transport=transport,
        )
        self.analyses = EphemeralAnalysesResource(self._http)
        self.runs = EphemeralRunsResource(self._http)
        self.classifications = EphemeralClassificationsResource(self._http)
        self.extractions = EphemeralExtractionsResource(self._http)

    def version(self) -> str:
        """Version du backend (`GET /api/version`)."""
        return str(self._http.get_json("/version")["version"])

    def analyze(
        self,
        files: Iterable[FileInput],
        analysis_config: EphemeralAnalysisConfig | None = None,
        ttl_hours: int | None = TTL_DEFAULT_HOURS,
        persist: bool = False,
        timeout: float | None = 300,
        *,
        analyse_id: uuid.UUID | str | None = None,
        poll_interval: float = 2,
        cleanup: bool = False,
    ) -> EphemeralRun:
        """One-liner : crée l'analyse éphémère, lance le run, attend le résultat.

        Fournir `analysis_config` (l'analyse est créée) ou `analyse_id` (analyse existante réutilisée).
        `persist` s'applique au run ; l'analyse suit `analysis_config.persist`.
        `cleanup=True` supprime le run (et le résultat conservé côté serveur) une fois celui-ci récupéré, ainsi
        que l'analyse créée ici si elle existe encore : le `EphemeralRun` renvoyé est alors un instantané.
        `WaitTimeoutError` est levée si `timeout` est dépassé (le run continue côté serveur).
        """
        if (analysis_config is None) == (analyse_id is None):
            raise ValueError("Fournir exactement un de analysis_config ou analyse_id.")
        created_analyse_id: uuid.UUID | None = None
        if analysis_config is not None:
            created = self.analyses.create_from_config(analysis_config)
            created_analyse_id = created.id
            analyse_id = created.id
        assert analyse_id is not None
        try:
            run = self.runs.create(analyse_id, files, persist=persist, ttl_hours=ttl_hours)
            result = self.runs.wait(run.id, timeout=timeout, poll_interval=poll_interval)
        except BaseException:
            # L'analyse créée ici ne doit pas fuir si le run n'a jamais pu démarrer.
            if created_analyse_id is not None and cleanup:
                self._quiet_delete_analyse(created_analyse_id)
            raise
        if cleanup:
            self.runs.delete(run.id)
            if created_analyse_id is not None:
                # Une analyse persist=false est déjà supprimée par le serveur à la fin du run.
                with contextlib.suppress(NotFoundError):
                    self.analyses.delete(created_analyse_id)
        return result

    def classify(
        self,
        file: FileInput,
        labels: Sequence[LabelDefinitionIn | dict[str, str]],
        *,
        multi_label: bool = False,
        prompt: str = "",
        persist: bool = False,
        ttl_hours: int | None = TTL_DEFAULT_HOURS,
        timeout: float | None = 300,
        poll_interval: float = 2,
        cleanup: bool = False,
    ) -> EphemeralClassification:
        """One-liner : classe les pages d'un document et attend le résultat.

        `cleanup=True` supprime le run (et le résultat conservé côté serveur) une fois celui-ci récupéré.
        `WaitTimeoutError` est levée si `timeout` est dépassé (le run continue côté serveur)."""
        run = self.classifications.create(
            file, labels, multi_label=multi_label, prompt=prompt, persist=persist, ttl_hours=ttl_hours
        )
        result = self.classifications.wait(run.run_id, timeout=timeout, poll_interval=poll_interval)
        if cleanup:
            self.runs.delete(result.run_id)
        return result

    def extract(
        self,
        file: FileInput,
        entities: Sequence[EntityDefinitionIn | dict[str, str]],
        *,
        prompt: str = "",
        persist: bool = False,
        ttl_hours: int | None = TTL_DEFAULT_HOURS,
        timeout: float | None = 300,
        poll_interval: float = 2,
        cleanup: bool = False,
    ) -> EphemeralExtraction:
        """One-liner : extrait les entités d'un document et attend le résultat (voir `classify` pour les options)."""
        run = self.extractions.create(file, entities, prompt=prompt, persist=persist, ttl_hours=ttl_hours)
        result = self.extractions.wait(run.run_id, timeout=timeout, poll_interval=poll_interval)
        if cleanup:
            self.runs.delete(result.run_id)
        return result

    def _quiet_delete_analyse(self, analyse_id: uuid.UUID) -> None:
        try:
            self.analyses.delete(analyse_id)
        except Exception:  # noqa: BLE001 - nettoyage au mieux, l'erreur d'origine prime
            pass

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> EphemeralClient:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.close()
