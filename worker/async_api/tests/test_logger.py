"""Le journal porte le contexte de la tâche, et le client HTTP n'y écrit pas ses URL."""

import io
import logging

from loguru import logger

import src.logger


def test_contextualized_task_id_appears_in_the_line() -> None:
    # Arrange : un puits de test, avec le formateur du module (le puits stdout est posé à l'import).
    tampon = io.StringIO()
    puits = logger.add(tampon, format=src.logger._formatter, colorize=False)

    # Act
    with logger.contextualize(task_id="tache-42"):
        logger.info("bonjour")
    logger.remove(puits)

    # Assert
    assert "task_id=tache-42" in tampon.getvalue()
    assert "bonjour" in tampon.getvalue()


def test_httpx_logger_is_quieted_to_warning() -> None:
    # Assert
    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("httpcore").level >= logging.WARNING
