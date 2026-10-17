"""Les codes d'erreur rendus au consommateur : stables, uniques, et au format `CODE: détail`."""

import re

import src.exceptions as exceptions
from src.exceptions import ECHEC_TECHNIQUE, MilleFeuilleBridgeError

_MOTIF_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _classes() -> list[type[MilleFeuilleBridgeError]]:
    return [
        cls
        for cls in vars(exceptions).values()
        if isinstance(cls, type) and issubclass(cls, MilleFeuilleBridgeError) and cls is not MilleFeuilleBridgeError
    ]


def test_every_error_carries_a_screaming_snake_case_code() -> None:
    # Act
    codes = [cls.error_code for cls in _classes()]

    # Assert
    assert codes
    assert all(_MOTIF_CODE.match(code) for code in codes), codes


def test_error_codes_are_unique() -> None:
    # Act
    codes = [cls.error_code for cls in _classes()]

    # Assert
    assert len(codes) == len(set(codes)), codes


def test_error_keeps_its_detail_for_the_consumer() -> None:
    # Arrange
    erreur = exceptions.FileTooLargeError("Le fichier a.pdf pèse 60 octets, maximum 50.")

    # Assert
    assert erreur.detail == "Le fichier a.pdf pèse 60 octets, maximum 50."
    assert str(erreur) == erreur.detail


def test_technical_failure_label_follows_the_code_convention() -> None:
    # Assert
    assert re.match(r"^[A-Z_]+: ", ECHEC_TECHNIQUE)
