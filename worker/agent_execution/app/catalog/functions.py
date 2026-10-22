"""Les outils internes du catalogue, tels que le modèle les voit : un nom de fonction, une description, un schéma
d'arguments. Un outil de la plateforme (`calcul_dates`) peut donner plusieurs fonctions au modèle.

Les identifiants d'outils (`calculatrice`, `calcul_dates`) sont ceux du backend (`internal_catalog.py`) : un agent y
fait référence. Seuls ceux de `FUNCTIONS_BY_TOOL` sont exécutables ici."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.catalog.tools import dates_basic, dates_duration
from app.catalog.tools.calculator import calculate
from app.catalog.tools.clock import SystemClock
from app.catalog.tools.errors import ToolError


@dataclass(frozen=True)
class CatalogFunction:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., dict]

    def definition(self) -> dict[str, Any]:
        """Au format du function calling OpenAI."""
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }

    def run(self, arguments: dict[str, Any]) -> str:
        """Exécute la fonction ; renvoie toujours du JSON, jamais une exception : le modèle lit l'erreur et corrige."""
        try:
            result = self.handler(**arguments)
        except ToolError as error:
            result = error.to_dict()
        except TypeError:
            # Argument manquant, en trop ou mal nommé : on dit au modèle ce qui est attendu.
            expected = ", ".join(self.parameters.get("properties", {})) or "aucun"
            result = ToolError("arguments_invalides", f"Arguments attendus : {expected}.").to_dict()
        return json.dumps(result, ensure_ascii=False)


def _params(properties: dict[str, dict], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def _date(description: str) -> dict[str, str]:
    return {"type": "string", "description": f"{description} Format AAAA-MM-JJ (ex. 2026-03-03)."}


def _integer(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}


_CLOCK = SystemClock()

CALCULATOR = (
    CatalogFunction(
        "calculer",
        "Calcule une expression arithmétique exactement (montants, taux, totaux, pourcentages) : + - * / // ** et "
        "parenthèses, avec round(x, n), abs, min, max. Utilise-la plutôt que de calculer de tête. La virgule décimale "
        "est acceptée hors des fonctions ; dans round(x, 2) écris les décimales avec un point.",
        _params(
            {"expression": {"type": "string", "description": "Ex. : 1234.50 * 1.2 ou round(100 / 3, 2)."}},
            ["expression"],
        ),
        lambda expression: calculate(expression),
    ),
)

DATES = (
    CatalogFunction(
        "jour_de_la_semaine",
        "Donne le jour de la semaine d'une date (en français).",
        _params({"date": _date("La date.")}, ["date"]),
        lambda date: dates_basic.weekday_fr(date),
    ),
    CatalogFunction(
        "ajouter_une_duree",
        "Ajoute une durée (années, mois, semaines, jours) à une date ; une valeur négative retire. "
        "Gère la fin de mois.",
        _params(
            {
                "date": _date("La date de départ."),
                "annees": _integer("Années à ajouter (0 par défaut)."),
                "mois": _integer("Mois à ajouter (0 par défaut)."),
                "semaines": _integer("Semaines à ajouter (0 par défaut)."),
                "jours": _integer("Jours à ajouter (0 par défaut)."),
            },
            ["date"],
        ),
        lambda date, annees=0, mois=0, semaines=0, jours=0: dates_duration.add_duration(
            date, years=annees, months=mois, weeks=semaines, days=jours
        ),
    ),
    CatalogFunction(
        "ecart_entre_dates",
        "Écart entre deux dates en années, mois entiers puis jours restants (ex. pour un âge ou une ancienneté).",
        _params(
            {"debut": _date("La date la plus ancienne."), "fin": _date("La date la plus récente.")}, ["debut", "fin"]
        ),
        lambda debut, fin: dates_duration.diff_ymd(debut, fin),
    ),
    CatalogFunction(
        "ecart_en_jours",
        "Écart entre deux dates en jours, en semaines et en mois entiers (ex. pour un délai).",
        _params(
            {"debut": _date("La date la plus ancienne."), "fin": _date("La date la plus récente.")}, ["debut", "fin"]
        ),
        lambda debut, fin: dates_duration.diff_calendar(debut, fin),
    ),
    CatalogFunction(
        "bornes_du_mois",
        "Premier et dernier jour du mois d'une date.",
        _params({"date": _date("Une date du mois.")}, ["date"]),
        lambda date: dates_basic.month_bounds(date),
    ),
    CatalogFunction(
        "bornes_du_trimestre",
        "Numéro du trimestre d'une date, et son premier et dernier jour.",
        _params({"date": _date("Une date du trimestre.")}, ["date"]),
        lambda date: dates_basic.quarter_bounds(date),
    ),
    CatalogFunction(
        "semaine_iso",
        "Année et numéro de la semaine ISO d'une date.",
        _params({"date": _date("La date.")}, ["date"]),
        lambda date: dates_basic.iso_week(date),
    ),
    CatalogFunction(
        "comparer_dates",
        "Dit si la date a est avant, après ou le même jour que la date b, et l'écart en jours.",
        _params({"a": _date("La première date."), "b": _date("La seconde date.")}, ["a", "b"]),
        lambda a, b: dates_basic.compare_dates(a, b),
    ),
    CatalogFunction(
        "date_dans_la_periode",
        "Dit si une date est dans une période [début, fin].",
        _params(
            {
                "date": _date("La date à vérifier."),
                "debut": _date("Début de la période."),
                "fin": _date("Fin de la période."),
                "inclusif": {"type": "boolean", "description": "Les bornes comptent (vrai par défaut)."},
            },
            ["date", "debut", "fin"],
        ),
        lambda date, debut, fin, inclusif=True: dates_basic.is_within(date, debut, fin, inclusif),
    ),
    CatalogFunction(
        "date_et_heure_actuelles",
        "Donne la date et l'heure d'aujourd'hui. À utiliser dès qu'un calcul dépend de la date du jour.",
        _params({"fuseau": {"type": "string", "description": "Fuseau horaire (Europe/Paris par défaut)."}}, []),
        lambda fuseau="Europe/Paris": dates_basic.current_datetime(_CLOCK, fuseau),
    ),
)

# Identifiant d'outil de la plateforme -> les fonctions qu'il donne au modèle.
FUNCTIONS_BY_TOOL: dict[str, tuple[CatalogFunction, ...]] = {"calculatrice": CALCULATOR, "calcul_dates": DATES}
