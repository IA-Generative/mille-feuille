"""Compteurs métier du worker `mille-feuille`, en complément des métriques génériques de `mic_worker`.

**Ce que les métriques génériques ne disent pas.** `worker_tasks_total` compte des tâches et
`worker_task_duration_seconds` mesure leur durée vue du pont. Ce service est un pont : ce qui
compte, c'est ce qui se passe de l'autre côté — combien de temps un run attend AVANT de démarrer
dans mille-feuille (`run_wait_seconds`, LE signal de contre-pression : quand il monte, le pont
pousse plus que mille-feuille n'absorbe), combien il dure une fois parti, combien de pages il a
traitées, de quelle classe sont les erreurs amont, et combien pèse le résultat déposé (ce qui
justifie la borne du résumé).

**Cardinalité close, aucun label d'identité.** `etat` ∈ `EtatRun`, `classe` ∈ `ClasseErreurAmont`.
Aucun `client_id`, aucun `task_id`, aucun nom de fichier : le registre est partagé avec la plateforme.
"""

from __future__ import annotations

from typing import Final

from mic_worker.metrics import REGISTRE
from prometheus_client import Counter, Histogram

_PREFIXE: Final = "mille_feuille"

#: Runs conclus, par issue vue du pont (`EtatRun`).
RUNS_TOTAL: Final = Counter(
    f"{_PREFIXE}_runs_total",
    "Runs mille-feuille conclus par ce worker, par issue.",
    ["etat"],
    registry=REGISTRE,
)

#: Durée d'un run côté mille-feuille, de sa création à sa fin (seaux de 10 s à 15 min : la classe `long`).
RUN_DURATION_SECONDS: Final = Histogram(
    f"{_PREFIXE}_run_duration_seconds",
    "Durée d'un run mille-feuille, de sa création à son état terminal.",
    buckets=(10, 30, 60, 120, 300, 600, 900),
    registry=REGISTRE,
)

#: Attente d'un run avant sa première étape : le temps passé dans les files Celery de mille-feuille.
RUN_WAIT_SECONDS: Final = Histogram(
    f"{_PREFIXE}_run_wait_seconds",
    "Attente d'un run mille-feuille entre sa création et le début de sa première étape (contre-pression).",
    buckets=(1, 5, 15, 30, 60, 120, 300, 600),
    registry=REGISTRE,
)

#: Pages traitées, toutes tâches confondues.
PAGES_TOTAL: Final = Counter(
    f"{_PREFIXE}_pages_total",
    "Pages des documents traités par les runs conclus avec succès.",
    registry=REGISTRE,
)

#: Erreurs rendues par le backend mille-feuille, par classe (`ClasseErreurAmont`).
UPSTREAM_ERRORS_TOTAL: Final = Counter(
    f"{_PREFIXE}_upstream_errors_total",
    "Erreurs du service d'analyse mille-feuille vues par ce worker, par classe.",
    ["classe"],
    registry=REGISTRE,
)

#: Taille du run complet déposé sur le stockage (ce qui justifie la borne du résumé).
RESULTAT_OCTETS: Final = Histogram(
    f"{_PREFIXE}_resultat_octets",
    "Taille en octets du résultat complet d'un run, déposé sur le stockage d'async-api.",
    buckets=(64 * 1024, 256 * 1024, 1024 * 1024, 4 * 1024 * 1024, 16 * 1024 * 1024, 64 * 1024 * 1024),
    registry=REGISTRE,
)
