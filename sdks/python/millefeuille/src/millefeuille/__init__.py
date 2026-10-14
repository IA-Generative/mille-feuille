"""SDK Python pour la plateforme mille-feuille (API REST persistante)."""

from millefeuille.client import MilleFeuilleClient
from millefeuille.exceptions import (
    AuthenticationError,
    ConflictError,
    ConnectionFailedError,
    MilleFeuilleError,
    NotFoundError,
    ServerError,
    ValidationError,
    WaitTimeoutError,
)
from millefeuille.models import Analyse, Dossier, DossierStatus

__version__ = "0.1.1"

__all__ = [
    "Analyse",
    "AuthenticationError",
    "ConflictError",
    "ConnectionFailedError",
    "MilleFeuilleClient",
    "MilleFeuilleError",
    "Dossier",
    "DossierStatus",
    "NotFoundError",
    "ServerError",
    "ValidationError",
    "WaitTimeoutError",
]
