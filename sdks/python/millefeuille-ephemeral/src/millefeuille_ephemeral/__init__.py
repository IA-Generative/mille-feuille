"""SDK Python pour l'API éphémère de mille-feuille (analyses et runs à la volée avec TTL)."""

from millefeuille_ephemeral.client import EphemeralClient
from millefeuille_ephemeral.exceptions import (
    AuthenticationError,
    ConflictError,
    ConnectionFailedError,
    MilleFeuilleError,
    NotFoundError,
    ServerError,
    TTLValidationError,
    ValidationError,
    WaitTimeoutError,
)
from millefeuille_ephemeral.models import (
    AgentDefinition,
    EphemeralAnalyse,
    EphemeralAnalysisConfig,
    EphemeralClassification,
    EphemeralExtraction,
    EphemeralRun,
    EphemeralRunSummary,
)

__version__ = "0.2.0"

__all__ = [
    "AgentDefinition",
    "AuthenticationError",
    "ConflictError",
    "ConnectionFailedError",
    "MilleFeuilleError",
    "EphemeralAnalysisConfig",
    "EphemeralAnalyse",
    "EphemeralClassification",
    "EphemeralClient",
    "EphemeralExtraction",
    "EphemeralRun",
    "EphemeralRunSummary",
    "NotFoundError",
    "ServerError",
    "TTLValidationError",
    "ValidationError",
    "WaitTimeoutError",
]
