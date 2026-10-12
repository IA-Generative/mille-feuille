import re
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.catalog.tools.errors import ToolError

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)
MIN_YEAR = 1900
MAX_YEAR = 2200
DATE_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_date(texte) -> date:
    """Lit une date ISO « AAAA-MM-JJ » ou lève ToolError."""
    if not isinstance(texte, str) or not DATE_ISO.fullmatch(texte):
        raise ToolError(
            "date_invalide",
            "La date doit être au format AAAA-MM-JJ, par exemple 2026-03-03.",
            {"valeur": texte},
        )
    try:
        jour = date.fromisoformat(texte)
    except ValueError:
        raise ToolError(
            "date_invalide",
            f"La date {texte} n'existe pas.",
            {"valeur": texte},
        ) from None
    if not MIN_YEAR <= jour.year <= MAX_YEAR:
        raise ToolError(
            "date_hors_bornes",
            f"L'année doit être comprise entre {MIN_YEAR} et {MAX_YEAR}.",
            {"valeur": texte},
        )
    return jour


def _parse_tz(nom) -> ZoneInfo:
    """Renvoie le fuseau IANA demandé ou lève ToolError."""
    try:
        return ZoneInfo(nom)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ToolError(
            "fuseau_inconnu",
            f"Le fuseau horaire {nom!r} est inconnu. Exemple : Europe/Paris.",
            {"valeur": nom},
        ) from None


def _format_day(d: date) -> str:
    """« 1er mars » pour le 1er du mois, « 2 mars », « 3 mars »… pour les autres."""
    jour = "1er" if d.day == 1 else str(d.day)
    return f"{jour} {MOIS[d.month - 1]}"
