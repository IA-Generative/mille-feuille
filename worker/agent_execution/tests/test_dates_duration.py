from datetime import date

import pytest

from app.catalog.tools.dates_duration import (
    _add_months,
    _join_fr,
    _libelle,
    _whole_months,
    add_duration,
    diff_calendar,
    diff_ymd,
    plural,
)
from app.catalog.tools.errors import ToolError


def code_of(fonction, *args, **kwargs) -> str:
    """Appelle la fonction, qui doit lever ToolError, et renvoie le code de l'erreur."""
    with pytest.raises(ToolError) as exc:
        fonction(*args, **kwargs)
    return exc.value.code


@pytest.mark.parametrize(
    ("n", "mot", "attendu"),
    [(0, "jour", "0 jour"), (1, "jour", "1 jour"), (2, "jour", "2 jours"), (2, "mois", "2 mois"), (3, "an", "3 ans")],
)
def test_plural(n, mot, attendu):
    assert plural(n, mot) == attendu


@pytest.mark.parametrize(
    ("depart", "mois", "attendu"),
    [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2024, 1, 31), 1, date(2024, 2, 29)),  # année bissextile
        (date(2026, 3, 30), 1, date(2026, 4, 30)),
        (date(2024, 2, 29), 12, date(2025, 2, 28)),
        (date(2024, 2, 29), 48, date(2028, 2, 29)),
        (date(2026, 3, 31), -1, date(2026, 2, 28)),  # retrait
        (date(2026, 1, 15), -1, date(2025, 12, 15)),  # passage d'année vers le passé
    ],
)
def test_add_months(depart, mois, attendu):
    assert _add_months(depart, mois) == attendu


# ---------- Assistants de libellé ----------


@pytest.mark.parametrize(
    ("parties", "attendu"),
    [
        (["5 jours"], "5 jours"),
        (["1 mois", "10 jours"], "1 mois et 10 jours"),
        (["2 ans", "3 mois", "4 jours"], "2 ans, 3 mois et 4 jours"),
    ],
)
def test_join_fr(parties, attendu):
    assert _join_fr(parties) == attendu


@pytest.mark.parametrize(
    ("parties", "attendu"),
    [
        ([(0, "an"), (0, "mois"), (0, "jour")], "0 jour"),  # tout à zéro
        ([(2, "an"), (0, "mois"), (0, "jour")], "2 ans"),  # parties nulles omises
        ([(0, "an"), (11, "mois"), (30, "jour")], "11 mois et 30 jours"),
        ([(2, "an"), (3, "mois"), (4, "jour")], "2 ans, 3 mois et 4 jours"),
    ],
)
def test_libelle(parties, attendu):
    assert _libelle(parties) == attendu


@pytest.mark.parametrize(
    ("debut", "fin", "attendu"),
    [
        (date(2026, 3, 3), date(2026, 3, 3), 0),
        (date(2026, 1, 15), date(2026, 3, 15), 2),  # le quantième est atteint
        (date(2026, 1, 15), date(2026, 3, 10), 1),  # le dernier mois n'est pas terminé
        (date(2026, 1, 31), date(2026, 2, 28), 0),  # le 31 n'est pas atteint
    ],
)
def test_whole_months(debut, fin, attendu):
    assert _whole_months(debut, fin) == attendu


# ---------- add_duration ----------


@pytest.mark.parametrize(
    ("depart", "duree", "attendu"),
    [
        ("2026-01-31", {"months": 1}, "2026-02-28"),  # fin de mois
        ("2024-01-31", {"months": 1}, "2024-02-29"),  # année bissextile
        ("2026-03-30", {"months": 1}, "2026-04-30"),
        ("2024-02-29", {"years": 1}, "2025-02-28"),
        ("2024-02-29", {"years": 4}, "2028-02-29"),
        ("2026-03-03", {"months": 2}, "2026-05-03"),
        ("2026-03-03", {"days": 30}, "2026-04-02"),
        ("2026-03-03", {"weeks": 2}, "2026-03-17"),
        ("2026-03-31", {"months": -1}, "2026-02-28"),  # retrait
        ("2026-01-15", {"days": -15}, "2025-12-31"),  # passage d'année
        ("2026-01-31", {"months": 1, "days": 1}, "2026-03-01"),  # mois d'abord, jours ensuite
        ("2026-03-03", {"years": 1, "months": 1, "weeks": 1, "days": 1}, "2027-04-11"),
        ("2026-03-03", {}, "2026-03-03"),  # durée nulle
    ],
)
def test_add_duration(depart, duree, attendu):
    assert add_duration(depart, **duree)["date"] == attendu


def test_add_duration_output():
    assert add_duration("2026-02-03", days=56) == {"ok": True, "date": "2026-03-31", "libelle": "mardi 31 mars 2026"}


def test_add_duration_label_first_of_month():
    assert add_duration("2026-06-20", days=11)["libelle"] == "mercredi 1er juillet 2026"


@pytest.mark.parametrize(
    "duree",
    [{"years": 500}, {"months": 2401}, {"days": 100001}, {"weeks": 15000}],
)
def test_add_duration_rejects_huge_durations(duree):
    assert code_of(add_duration, "2026-03-03", **duree) == "duree_hors_bornes"


@pytest.mark.parametrize(
    ("depart", "duree"),
    [("2200-01-01", {"years": 100}), ("1900-01-01", {"days": -1})],
)
def test_add_duration_rejects_out_of_range_result(depart, duree):
    assert code_of(add_duration, depart, **duree) == "duree_hors_bornes"


@pytest.mark.parametrize("valeur", [True, 1.5, "2", None])
@pytest.mark.parametrize("nom", ["years", "months", "weeks", "days"])
def test_add_duration_rejects_non_integers(nom, valeur):
    assert code_of(add_duration, "2026-03-03", **{nom: valeur}) == "duree_invalide"


def test_add_duration_rejects_bad_start_date():
    assert code_of(add_duration, "2026-02-31", days=1) == "date_invalide"


# ---------- diff_calendar ----------


def test_diff_calendar_issue_example():
    assert diff_calendar("2026-01-01", "2026-02-11") == {
        "ok": True,
        "jours": 41,
        "semaines": 5,
        "reste_jours": 6,
        "mois_entiers": 1,
        "libelle": "1 mois et 10 jours",
    }


def test_diff_calendar_days_in_non_leap_year():
    assert diff_calendar("2026-01-01", "2026-03-01")["jours"] == 59


def test_diff_calendar_days_in_leap_year():
    assert diff_calendar("2024-01-01", "2024-03-01")["jours"] == 60


def test_diff_calendar_same_day():
    assert diff_calendar("2026-03-03", "2026-03-03") == {
        "ok": True,
        "jours": 0,
        "semaines": 0,
        "reste_jours": 0,
        "mois_entiers": 0,
        "libelle": "0 jour",
    }


def test_diff_calendar_across_year_end():
    assert diff_calendar("2025-12-30", "2026-01-02")["jours"] == 3


def test_diff_calendar_whole_months_are_not_grouped_in_years():
    result = diff_calendar("2023-11-30", "2026-03-03")
    assert result["mois_entiers"] == 27
    assert result["libelle"] == "27 mois et 3 jours"


# ---------- diff_ymd ----------


def test_diff_ymd_issue_example():
    result = diff_ymd("2023-12-03", "2026-03-07")
    assert (result["annees"], result["mois"], result["jours"]) == (2, 3, 4)
    assert result["libelle"] == "2 ans, 3 mois et 4 jours"


def test_diff_ymd_leap_day_to_end_of_february():
    # Choix documenté : diff_ymd compte les mois selon le quantième de départ (le 29), sans la règle de
    # repli de fin de mois d'add_duration. Du 29 février 2024 au 28 février 2025, le 29 n'est jamais
    # atteint : on obtient donc 11 mois et 30 jours, et non « 1 an » (alors que add_duration avec
    # years=1 donne bien le 28 février 2025). Les deux fonctions ne sont pas l'inverse exact l'une de l'autre.
    result = diff_ymd("2024-02-29", "2025-02-28")
    assert (result["annees"], result["mois"], result["jours"]) == (0, 11, 30)
    assert result["libelle"] == "11 mois et 30 jours"


def test_diff_ymd_same_day():
    assert diff_ymd("2026-03-03", "2026-03-03") == {"ok": True, "annees": 0, "mois": 0, "jours": 0, "libelle": "0 jour"}


@pytest.mark.parametrize(
    ("start", "end", "attendu"),
    [
        ("2023-11-30", "2026-03-03", (2, 3, 3)),  # plus de 2 ans
        ("2020-01-15", "2022-01-15", (2, 0, 0)),
        ("2024-02-29", "2028-02-29", (4, 0, 0)),
        ("2026-01-31", "2026-03-01", (0, 1, 1)),
        ("2026-03-03", "2026-03-04", (0, 0, 1)),
    ],
)
def test_diff_ymd(start, end, attendu):
    result = diff_ymd(start, end)
    assert (result["annees"], result["mois"], result["jours"]) == attendu


# ---------- erreurs des deux diff ----------


@pytest.mark.parametrize("fonction", [diff_ymd, diff_calendar])
def test_diff_rejects_reversed_period(fonction):
    assert code_of(fonction, "2026-03-10", "2026-03-03") == "periode_inversee"


@pytest.mark.parametrize("fonction", [diff_ymd, diff_calendar])
def test_diff_rejects_bad_dates(fonction):
    assert code_of(fonction, "2026-02-31", "2026-03-03") == "date_invalide"
    assert code_of(fonction, "2026-03-03", "pas une date") == "date_invalide"
    assert code_of(fonction, "1800-01-01", "2026-03-03") == "date_hors_bornes"
