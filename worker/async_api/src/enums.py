"""Les chaînes du contrat, nommées une fois : outils d'agent ouverts à la plateforme, états d'un run,
classes d'erreur amont."""

from enum import StrEnum


class OutilAgent(StrEnum):
    """Les outils d'agent que la plateforme laisse employer — ceux qui restent dans le dossier.

    `recherche_web`, `base_connaissances` et `appel_agent` existent dans mille-feuille mais sont
    fermés ici : une consigne venue d'un consommateur ne doit pas pouvoir faire sortir un agent
    du dossier (exfiltration, coût non borné). Même liste que l'énumération `tools` du schéma.
    """

    LECTURE_DOCUMENT = "lecture_document"
    CALCULATRICE = "calculatrice"
    VERIFICATION_COHERENCE = "verification_coherence"


class EtatRun(StrEnum):
    """Comment une tâche s'est conclue, vu du worker (label `etat` des métriques, cardinalité close)."""

    TERMINE = "termine"
    ECHEC = "echec"
    ARRETE = "arrete"
    DELAI = "delai"
    REPRIS = "repris"


class ClasseErreurAmont(StrEnum):
    """Famille d'une erreur rendue par le backend mille-feuille (label `classe` des métriques)."""

    QUATRE_CENTS = "4xx"
    CINQ_CENTS = "5xx"
    RESEAU = "reseau"
