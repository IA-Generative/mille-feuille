from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Source de « maintenant » injectée dans les tools : toujours un datetime avec fuseau."""

    def now(self) -> datetime: ...

    # Le ... signifie « pas d'implémentation ici » : c'est seulement la signature.


class SystemClock:
    """Horloge réelle : renvoie l'heure courante en UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Horloge figée pour les tests : renvoie toujours l'instant donné (avec fuseau obligatoire)."""

    def __init__(self, instant: datetime):
        if instant.tzinfo is None:
            raise ValueError("FixedClock exige un datetime avec fuseau")
        self._instant = instant

    def now(self) -> datetime:
        return self._instant
