"""Les compteurs métier bougent avec l'issue de la tâche, et leurs labels restent dans les énumérations."""

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from mic_worker import S3Client
from mic_worker.typed import IncomingMessage
from millefeuille.exceptions import ConnectionFailedError, ServerError
from millefeuille_ephemeral import EphemeralClient
from prometheus_client import CollectorRegistry

from src import metriques
from src.enums import ClasseErreurAmont, EtatRun
from src.task import AnalyzeTask
from tests.test_task import ANALYSE_ID, BODY, make_big_run, make_run


def _valeur(compteur: Any, **labels: str) -> float:
    return (compteur.labels(**labels) if labels else compteur)._value.get()


def _somme(histogramme: Any) -> float:
    return histogramme._sum.get()


def _tache(runs: list[Any], **kwargs: Any) -> tuple[AnalyzeTask, MagicMock]:
    s3 = MagicMock(spec=S3Client)
    s3.get_size = AsyncMock(return_value=10)
    s3.download = AsyncMock(return_value=b"%PDF")
    client = MagicMock(spec=EphemeralClient)
    client.analyses = MagicMock()
    client.analyses.create_from_config.return_value = MagicMock(id=uuid.UUID(ANALYSE_ID))
    client.runs = MagicMock()
    client.runs.create.return_value = make_run("en_cours", ("en_cours",))
    client.runs.get.side_effect = runs
    task = AnalyzeTask(
        s3, client, max_file_size=1000, max_total_size=1500, max_files=3, run_timeout=100.0, poll_interval=0, **kwargs
    )
    return task, client


async def test_successful_run_counts_termine_pages_duration_and_result_size() -> None:
    # Arrange
    avant = (
        _valeur(metriques.RUNS_TOTAL, etat=EtatRun.TERMINE.value),
        _valeur(metriques.PAGES_TOTAL),
        _somme(metriques.RESULTAT_OCTETS),
    )
    task, _ = _tache([make_big_run(pages=3)])

    # Act
    await task.execute(IncomingMessage(task_id="t", body=BODY), AsyncMock())

    # Assert
    assert _valeur(metriques.RUNS_TOTAL, etat=EtatRun.TERMINE.value) == avant[0] + 1
    assert _valeur(metriques.PAGES_TOTAL) == avant[1] + 3
    assert _somme(metriques.RESULTAT_OCTETS) > avant[2]


async def test_failed_run_counts_echec_not_pages() -> None:
    # Arrange
    avant = (_valeur(metriques.RUNS_TOTAL, etat=EtatRun.ECHEC.value), _valeur(metriques.PAGES_TOTAL))
    task, _ = _tache([make_run("échec", ("échec",))])

    # Act
    with pytest.raises(RuntimeError, match="^RUN_FAILED"):
        await task.execute(IncomingMessage(task_id="t", body=BODY), AsyncMock())

    # Assert
    assert _valeur(metriques.RUNS_TOTAL, etat=EtatRun.ECHEC.value) == avant[0] + 1
    assert _valeur(metriques.PAGES_TOTAL) == avant[1]


async def test_timed_out_run_counts_delai() -> None:
    # Arrange
    avant = _valeur(metriques.RUNS_TOTAL, etat=EtatRun.DELAI.value)
    ticks = iter(range(0, 1000, 60))
    task, _ = _tache([make_run("en_cours", ("en_cours",))] * 5, clock=lambda: float(next(ticks)))

    # Act
    with pytest.raises(RuntimeError, match="^RUN_TIMEOUT"):
        await task.execute(IncomingMessage(task_id="t", body=BODY), AsyncMock())

    # Assert
    assert _valeur(metriques.RUNS_TOTAL, etat=EtatRun.DELAI.value) == avant + 1


@pytest.mark.parametrize(
    ("erreur", "classe"),
    [
        (ServerError("x", status_code=503), ClasseErreurAmont.CINQ_CENTS),
        (ConnectionFailedError("x"), ClasseErreurAmont.RESEAU),
    ],
    ids=["5xx", "reseau"],
)
async def test_upstream_error_counts_its_class(erreur: Exception, classe: ClasseErreurAmont) -> None:
    # Arrange
    avant = _valeur(metriques.UPSTREAM_ERRORS_TOTAL, classe=classe.value)
    task, client = _tache([])
    client.runs.create.side_effect = erreur

    # Act
    with pytest.raises(RuntimeError, match="^UPSTREAM_ERROR"):
        await task.execute(IncomingMessage(task_id="t", body=BODY), AsyncMock())

    # Assert
    assert _valeur(metriques.UPSTREAM_ERRORS_TOTAL, classe=classe.value) == avant + 1


def test_metrics_live_in_the_shared_registry_with_the_module_prefix() -> None:
    # Assert
    registre: CollectorRegistry = metriques.REGISTRE
    noms = {metric.name for metric in registre.collect()}
    assert {"mille_feuille_runs", "mille_feuille_pages", "mille_feuille_run_duration_seconds"} <= noms
