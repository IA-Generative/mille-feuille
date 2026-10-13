# Règles de calcul (la raison d'être de ce module) :
# - Fin de mois : on ajoute des mois en gardant le quantième ; s'il n'existe pas, on prend le dernier
#   jour du mois. 31 janvier + 1 mois = 28 février 2026 (29 en 2024). 30 mars + 1 mois = 30 avril.
#   29 février 2024 + 1 an = 28 février 2025.
# - Durée mixte : on applique d'abord années + mois, puis semaines + jours.
# - diff_ymd : années entières, puis mois entiers, puis jours restants, du plus tôt au plus tard.

import calendar
from datetime import date, timedelta

from app.catalog.tools.dates_basic import JOURS, MAX_YEAR, MIN_YEAR, _format_day, _parse_date
from app.catalog.tools.errors import ToolError, ok

MAX_YEARS = 200
MAX_MONTHS = 2400
MAX_DAYS = 100000


def plural(n: int, mot: str) -> str:
    """« 1 jour », « 0 jour », « 2 jours », « 2 mois » : pas de s pour 0 et 1."""
    if n >= 2 and not mot.endswith("s"):
        mot += "s"
    return f"{n} {mot}"


def _add_months(d: date, n: int) -> date:
    """Ajoute n mois (négatif = retrait) en gardant le quantième, ou le dernier jour du mois."""
    # 1. Position du nouveau mois, en comptant à partir de 0 (janvier = 0, décembre = 11).
    position = d.month - 1 + n

    # 2. Chaque tranche de 12 mois fait changer l'année ; le reste donne le mois.
    annee = d.year + position // 12
    mois = position % 12 + 1

    # 3. Le jour du mois : le même qu'avant, sauf s'il n'existe pas dans ce mois.
    dernier_jour = calendar.monthrange(annee, mois)[1]
    jour = min(d.day, dernier_jour)

    return date(annee, mois, jour)


def _join_fr(parties: list[str]) -> str:
    """["2 ans", "3 mois", "4 jours"] devient "2 ans, 3 mois et 4 jours"."""
    if len(parties) == 1:
        return parties[0]
    return ", ".join(parties[:-1]) + " et " + parties[-1]


def _check_int(nom: str, valeur) -> None:
    """Lève ToolError si valeur n'est pas un nombre entier (les booléens sont refusés)."""
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        raise ToolError(
            "duree_invalide",
            f"{nom} doit être un nombre entier.",
            {nom: valeur},
        )


def add_duration(date_iso: str, years: int = 0, months: int = 0, weeks: int = 0, days: int = 0) -> dict:
    """Ajoute une durée à une date (valeurs négatives = retrait)."""
    depart = _parse_date(date_iso)
    for nom, valeur in (("years", years), ("months", months), ("weeks", weeks), ("days", days)):
        _check_int(nom, valeur)
    total_jours = weeks * 7 + days

    # Bornes de la durée demandée.
    if abs(years) > MAX_YEARS or abs(months) > MAX_MONTHS or abs(total_jours) > MAX_DAYS:
        raise ToolError(
            "duree_hors_bornes",
            "La durée demandée est trop grande.",
            {"years": years, "months": months, "weeks": weeks, "days": days},
        )

    # D'abord années + mois (règle de fin de mois), puis semaines + jours.
    resultat = _add_months(depart, years * 12 + months) + timedelta(days=total_jours)

    # Borne du résultat.
    if not MIN_YEAR <= resultat.year <= MAX_YEAR:
        raise ToolError(
            "duree_hors_bornes",
            f"Le résultat doit rester entre les années {MIN_YEAR} et {MAX_YEAR}.",
            {"resultat": resultat.isoformat()},
        )

    libelle = f"{JOURS[resultat.weekday()]} {_format_day(resultat)} {resultat.year}"
    return ok(date=resultat.isoformat(), libelle=libelle)


def _read_period(start: str, end: str) -> tuple[date, date]:
    """Lit les deux dates ; lève periode_inversee si la fin est avant le début."""
    debut = _parse_date(start)
    fin = _parse_date(end)
    if fin < debut:
        raise ToolError(
            "periode_inversee",
            f"La date de fin ({end}) est avant la date de début ({start}).",
            {"start": start, "end": end},
        )
    return debut, fin


def _whole_months(debut: date, fin: date) -> int:
    """Nombre de mois entiers écoulés entre deux dates (debut <= fin)."""
    mois = (fin.year - debut.year) * 12 + fin.month - debut.month
    if fin.day < debut.day:  # le dernier mois n'est pas terminé
        mois -= 1
    return mois


def _libelle(parties: list[tuple[int, str]]) -> str:
    """Assemble les parties non nulles : « 2 ans, 3 mois et 4 jours ». Tout à zéro : « 0 jour »."""
    morceaux = [plural(n, mot) for n, mot in parties if n > 0]
    return _join_fr(morceaux or [plural(0, "jour")])


def diff_ymd(start: str, end: str) -> dict:
    """Écart entre deux dates en années, mois entiers puis jours restants."""
    debut, fin = _read_period(start, end)

    # 1. Combien de mois entiers se sont écoulés au total ?
    mois_au_total = _whole_months(debut, fin)

    # 2. On range ces mois en années et en mois restants (12 mois = 1 an).
    annees = mois_au_total // 12
    mois = mois_au_total % 12

    # 3. Les jours restants : on avance la date de début de ces mois,
    #    puis on compte les jours qui la séparent de la date de fin.
    date_apres_les_mois = _add_months(debut, mois_au_total)
    jours = (fin - date_apres_les_mois).days

    libelle = _libelle([(annees, "an"), (mois, "mois"), (jours, "jour")])
    return ok(annees=annees, mois=mois, jours=jours, libelle=libelle)


def diff_calendar(start: str, end: str) -> dict:
    """Écart entre deux dates en jours, semaines et mois entiers."""
    debut, fin = _read_period(start, end)

    # 1. L'écart total en jours, puis en semaines complètes + jours restants.
    jours_au_total = (fin - debut).days
    semaines = jours_au_total // 7
    reste_jours = jours_au_total % 7

    # 2. Le nombre de mois entiers (sans les regrouper en années).
    mois_entiers = _whole_months(debut, fin)

    # 3. Les jours qui restent après ces mois entiers (pour le libellé).
    date_apres_les_mois = _add_months(debut, mois_entiers)
    jours_apres_les_mois = (fin - date_apres_les_mois).days

    libelle = _libelle([(mois_entiers, "mois"), (jours_apres_les_mois, "jour")])
    return ok(
        jours=jours_au_total,
        semaines=semaines,
        reste_jours=reste_jours,
        mois_entiers=mois_entiers,
        libelle=libelle,
    )
