"""La configuration tient-elle dans l'échéance d'acquittement du courtier, et refuse-t-elle de démarrer sinon ?"""

import pytest

from src.config import (
    BUDGET_TACHE_MAX_S,
    DEBIT_DEPOT_MIN_OCTETS_S,
    DELAI_TRANSFERTS_MAX_S,
    ECHEANCE_ACQUITTEMENT_S,
    MAX_FILES_PLATEFORME,
    TTL_MAX_PLATEFORME,
    Settings,
    settings,
)

_OCTETS_PAR_MIO = 1024 * 1024


def test_default_queues_are_the_catalogue_queues() -> None:
    assert settings.IN_QUEUE_NAME == "mille_feuille_queue_in"
    assert settings.OUT_QUEUE_NAME == "mille_feuille_queue_out"


def test_default_run_budget_fits_under_the_ack_deadline() -> None:
    # Arrange : attente du run + transferts + nettoyage (trois appels au délai de requête).
    budget = settings.RUN_TIMEOUT_SECONDS + DELAI_TRANSFERTS_MAX_S + 3 * settings.MILLEFEUILLE_REQUEST_TIMEOUT

    # Assert
    assert budget <= BUDGET_TACHE_MAX_S < ECHEANCE_ACQUITTEMENT_S


def test_default_bounds_are_coherent() -> None:
    assert settings.MAX_FILE_SIZE_BYTES == 50 * _OCTETS_PAR_MIO
    assert settings.MAX_FILE_SIZE_BYTES <= settings.MAX_TOTAL_SIZE_BYTES
    assert settings.MAX_FILES == MAX_FILES_PLATEFORME
    assert settings.MAX_TOTAL_SIZE_BYTES / DEBIT_DEPOT_MIN_OCTETS_S <= settings.MILLEFEUILLE_UPLOAD_TIMEOUT
    assert TTL_MAX_PLATEFORME == 168


def test_settings_refuse_a_run_timeout_beyond_the_budget() -> None:
    # Act / Assert : 2 000 s d'attente ne tiennent pas sous les 1 080 s du budget.
    with pytest.raises(ValueError, match="dépasse le budget"):
        Settings(RUN_TIMEOUT_SECONDS=2000)


def test_settings_refuse_a_file_bound_above_the_total_bound() -> None:
    with pytest.raises(ValueError, match="MAX_FILE_SIZE_BYTES"):
        Settings(MAX_FILE_SIZE_BYTES=200 * _OCTETS_PAR_MIO)


def test_settings_refuse_an_upload_timeout_too_short_for_the_total_bound() -> None:
    with pytest.raises(ValueError, match="MILLEFEUILLE_UPLOAD_TIMEOUT"):
        Settings(MILLEFEUILLE_UPLOAD_TIMEOUT=5)


@pytest.mark.parametrize("champ", ["POLL_INTERVAL_SECONDS", "WORKER_CONCURRENCY", "MAX_FILES"])
def test_settings_refuse_a_non_positive_cadence_or_count(champ: str) -> None:
    with pytest.raises(ValueError, match="strictement positifs"):
        Settings(**{champ: 0})
