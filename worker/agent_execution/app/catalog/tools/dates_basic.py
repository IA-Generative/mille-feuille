import calendar
import re
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.catalog.tools.clock import Clock
from app.catalog.tools.errors import ToolError, ok

# ---------- Vérification que les dates sont valides ----------

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


# ---------- Tools ----------


def weekday_fr(date_iso: str) -> dict:
    """Jour de la semaine en français (lundi = 1)."""
    jour = _parse_date(date_iso)
    numero = jour.isoweekday()
    return ok(jour=JOURS[numero - 1], numero_iso=numero)


def month_bounds(date_iso: str) -> dict:
    """Premier et dernier jour du mois de la date donnée."""
    jour = _parse_date(date_iso)
    dernier = calendar.monthrange(jour.year, jour.month)[1]
    return ok(
        debut=jour.replace(day=1).isoformat(),
        fin=jour.replace(day=dernier).isoformat(),
    )


def quarter_bounds(date_iso: str) -> dict:
    """Numéro du trimestre et premier / dernier jour de ce trimestre."""
    jour = _parse_date(date_iso)
    trimestre = (jour.month - 1) // 3 + 1
    mois_debut = (trimestre - 1) * 3 + 1
    mois_fin = trimestre * 3
    dernier = calendar.monthrange(jour.year, mois_fin)[1]
    return ok(
        trimestre=trimestre,
        debut=date(jour.year, mois_debut, 1).isoformat(),
        fin=date(jour.year, mois_fin, dernier).isoformat(),
    )


def iso_week(date_iso: str) -> dict:
    """Année et numéro de la semaine ISO de la date donnée."""
    jour = _parse_date(date_iso)
    resultat = jour.isocalendar()
    return ok(annee=resultat.year, semaine=resultat.week)


def compare_dates(a: str, b: str) -> dict:
    """Position de la date a par rapport à la date b, et écart en jours."""
    date_a = _parse_date(a)
    date_b = _parse_date(b)
    if date_a < date_b:
        relation = "avant"
    elif date_a > date_b:
        relation = "apres"
    else:
        relation = "meme_jour"
    return ok(relation=relation, jours_d_ecart=abs((date_b - date_a).days))


def is_within(date_iso: str, start: str, end: str, inclusive: bool = True) -> dict:
    """Indique si la date est dans la période [start, end]."""
    jour = _parse_date(date_iso)
    debut = _parse_date(start)
    fin = _parse_date(end)
    if debut > fin:
        raise ToolError(
            "periode_inversee",
            f"Le début de la période ({start}) est après sa fin ({end}).",
            {"start": start, "end": end},
        )
    if inclusive:
        dedans = debut <= jour <= fin
    else:
        dedans = debut < jour < fin
    return ok(dans_la_periode=dedans)


def current_datetime(clock: Clock, tz: str = "Europe/Paris") -> dict:
    """Date et heure actuelles dans le fuseau demandé, avec un libellé en français."""
    zone = _parse_tz(tz)
    maintenant = clock.now().astimezone(zone).replace(microsecond=0)
    jour = maintenant.date()
    nom_jour = JOURS[jour.weekday()]
    label = f"{nom_jour} {_format_day(jour)} {jour.year}, {maintenant.hour} h {maintenant.minute:02d}"
    return ok(iso=maintenant.isoformat(), date=jour.isoformat(), label=label)
