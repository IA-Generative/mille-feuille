"""Tests des dates de base du catalogue (dates_basic)."""

from datetime import UTC, date, datetime

import pytest

from app.catalog.tools.clock import FixedClock
from app.catalog.tools.dates_basic import (
    _format_day,
    _parse_date,
    _parse_tz,
    compare_dates,
    current_datetime,
    is_within,
    iso_week,
    month_bounds,
    quarter_bounds,
    weekday_fr,
)
from app.catalog.tools.errors import ToolError


def code_of(fonction, *args, **kwargs) -> str:
    """Appelle la fonction, qui doit lever ToolError, et renvoie le code de l'erreur."""
    with pytest.raises(ToolError) as exc:
        fonction(*args, **kwargs)
    return exc.value.code


# ---------- Assistants ----------


def test_parse_date_valid():
    assert _parse_date("2026-03-03") == date(2026, 3, 3)


@pytest.mark.parametrize("texte", ["1900-01-01", "2200-12-31"])
def test_parse_date_accepts_year_bounds(texte):
    assert _parse_date(texte).isoformat() == texte


@pytest.mark.parametrize(
    "texte", ["2026-02-31", "pas une date", "20260303", "2026-W10-2", "2026-3-3", "", None, 20260303]
)
def test_parse_date_invalid(texte):
    assert code_of(_parse_date, texte) == "date_invalide"


@pytest.mark.parametrize("texte", ["1800-01-01", "1899-12-31", "2201-01-01"])
def test_parse_date_out_of_bounds(texte):
    assert code_of(_parse_date, texte) == "date_hors_bornes"


def test_parse_tz_valid():
    assert str(_parse_tz("Europe/Paris")) == "Europe/Paris"


@pytest.mark.parametrize("nom", ["Mars/Olympus", "", "../x", None])
def test_parse_tz_unknown(nom):
    assert code_of(_parse_tz, nom) == "fuseau_inconnu"


def test_format_day_first_of_month_is_1er():
    assert _format_day(date(2026, 3, 1)) == "1er mars"


def test_format_day_other_days():
    assert _format_day(date(2026, 3, 2)) == "2 mars"
    assert _format_day(date(2026, 2, 10)) == "10 février"


# ---------- current_datetime ----------


def test_current_datetime_winter_time():
    clock = FixedClock(datetime(2026, 3, 3, 9, 0, tzinfo=UTC))
    assert current_datetime(clock, "Europe/Paris") == {
        "ok": True,
        "iso": "2026-03-03T10:00:00+01:00",
        "date": "2026-03-03",
        "label": "mardi 3 mars 2026, 10 h 00",
    }


def test_current_datetime_summer_time():
    clock = FixedClock(datetime(2026, 7, 1, 9, 0, tzinfo=UTC))
    result = current_datetime(clock, "Europe/Paris")
    assert result["iso"] == "2026-07-01T11:00:00+02:00"
    assert result["label"] == "mercredi 1er juillet 2026, 11 h 00"


def test_current_datetime_uses_paris_by_default():
    clock = FixedClock(datetime(2026, 3, 3, 9, 0, tzinfo=UTC))
    assert current_datetime(clock) == current_datetime(clock, "Europe/Paris")


def test_current_datetime_date_depends_on_timezone():
    clock = FixedClock(datetime(2026, 3, 1, 23, 30, tzinfo=UTC))
    assert current_datetime(clock, "UTC")["date"] == "2026-03-01"
    assert current_datetime(clock, "Asia/Tokyo")["date"] == "2026-03-02"


def test_current_datetime_unknown_timezone():
    clock = FixedClock(datetime(2026, 3, 3, 9, 0, tzinfo=UTC))
    assert code_of(current_datetime, clock, "Mars/Olympus") == "fuseau_inconnu"


# ---------- weekday_fr ----------


@pytest.mark.parametrize(
    ("texte", "jour", "numero"),
    [
        ("2026-03-02", "lundi", 1),
        ("2026-03-03", "mardi", 2),
        ("2026-01-31", "samedi", 6),
        ("2024-02-29", "jeudi", 4),  # année bissextile
    ],
)
def test_weekday_fr(texte, jour, numero):
    assert weekday_fr(texte) == {"ok": True, "jour": jour, "numero_iso": numero}


# ---------- compare_dates ----------


def test_compare_dates_same_day():
    assert compare_dates("2026-03-03", "2026-03-03") == {"ok": True, "relation": "meme_jour", "jours_d_ecart": 0}


def test_compare_dates_before():
    assert compare_dates("2026-03-03", "2026-03-15") == {"ok": True, "relation": "avant", "jours_d_ecart": 12}


def test_compare_dates_after():
    assert compare_dates("2026-03-15", "2026-03-03") == {"ok": True, "relation": "apres", "jours_d_ecart": 12}


def test_compare_dates_across_year_end():
    assert compare_dates("2025-12-30", "2026-01-02")["jours_d_ecart"] == 3


# ---------- is_within ----------


@pytest.mark.parametrize(
    ("texte", "inclusive", "attendu"),
    [
        ("2026-03-05", True, True),  # au milieu
        ("2026-03-05", False, True),
        ("2026-03-03", True, True),  # égale au début
        ("2026-03-03", False, False),
        ("2026-03-10", True, True),  # égale à la fin
        ("2026-03-10", False, False),
        ("2026-03-02", True, False),  # avant la période
        ("2026-03-11", True, False),  # après la période
    ],
)
def test_is_within(texte, inclusive, attendu):
    result = is_within(texte, "2026-03-03", "2026-03-10", inclusive=inclusive)
    assert result == {"ok": True, "dans_la_periode": attendu}


def test_is_within_reversed_period():
    assert code_of(is_within, "2026-03-05", "2026-03-10", "2026-03-03") == "periode_inversee"


# ---------- month_bounds ----------


@pytest.mark.parametrize(
    ("texte", "debut", "fin"),
    [
        ("2024-02-10", "2024-02-01", "2024-02-29"),  # année bissextile
        ("2026-02-10", "2026-02-01", "2026-02-28"),
        ("2026-12-05", "2026-12-01", "2026-12-31"),
        ("2026-04-30", "2026-04-01", "2026-04-30"),
    ],
)
def test_month_bounds(texte, debut, fin):
    assert month_bounds(texte) == {"ok": True, "debut": debut, "fin": fin}


# ---------- quarter_bounds ----------


@pytest.mark.parametrize(
    ("texte", "trimestre", "debut", "fin"),
    [
        ("2026-02-14", 1, "2026-01-01", "2026-03-31"),
        ("2026-05-20", 2, "2026-04-01", "2026-06-30"),
        ("2026-09-30", 3, "2026-07-01", "2026-09-30"),
        ("2026-12-31", 4, "2026-10-01", "2026-12-31"),
    ],
)
def test_quarter_bounds(texte, trimestre, debut, fin):
    assert quarter_bounds(texte) == {"ok": True, "trimestre": trimestre, "debut": debut, "fin": fin}


# ---------- iso_week ----------


@pytest.mark.parametrize(
    ("texte", "annee", "semaine"),
    [
        ("2026-03-03", 2026, 10),
        ("2026-12-31", 2026, 53),
        ("2027-01-01", 2026, 53),  # le 1er janvier 2027 est dans la semaine 53 de 2026
        ("2024-12-30", 2025, 1),  # fin décembre dans la semaine 1 de l'année suivante
    ],
)
def test_iso_week(texte, annee, semaine):
    assert iso_week(texte) == {"ok": True, "annee": annee, "semaine": semaine}


# ---------- erreurs ----------


@pytest.mark.parametrize("fonction", [weekday_fr, iso_week, month_bounds, quarter_bounds])
def test_single_date_functions_reject_bad_dates(fonction):
    assert code_of(fonction, "2026-02-31") == "date_invalide"
    assert code_of(fonction, "pas une date") == "date_invalide"
    assert code_of(fonction, "1800-01-01") == "date_hors_bornes"


def test_compare_dates_rejects_bad_dates():
    assert code_of(compare_dates, "2026-02-31", "2026-03-03") == "date_invalide"
    assert code_of(compare_dates, "2026-03-03", "1800-01-01") == "date_hors_bornes"


# ---------- contrat de sortie ----------


def test_current_datetime_output_contract():
    clock = FixedClock(datetime(2026, 3, 3, 9, 0, tzinfo=UTC))
    result = current_datetime(clock)
    assert result["ok"] is True
    assert result["label"]
    assert datetime.fromisoformat(result["iso"]).utcoffset() is not None
    assert date.fromisoformat(result["date"]) == date(2026, 3, 3)
