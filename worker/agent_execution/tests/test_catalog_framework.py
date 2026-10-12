"""Tests du cadre commun du catalogue : horloge, erreurs, bornes."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.catalog.tools.bounds import MAX_DATE_RANGE_YEARS, MAX_LIST_ITEMS, require
from app.catalog.tools.clock import FixedClock, SystemClock
from app.catalog.tools.errors import ToolError, ok

# ---------- Tests pour clock.py ----------

CATALOG_DIR = Path(__file__).resolve().parent.parent / "app" / "catalog"
FORBIDDEN = ("datetime.now", "date.today")


def test_system_clock_returns_aware_utc_datetime():
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_fixed_clock_always_returns_same_instant():
    instant = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
    clock = FixedClock(instant)
    assert clock.now() == instant
    assert clock.now() == clock.now()
    assert clock.now().tzinfo is not None


def test_fixed_clock_rejects_naive_datetime():
    with pytest.raises(ValueError):
        FixedClock(datetime(2024, 1, 15, 12, 0))


# Test permettant d'interdir de mettre datetime.now() ailleurs
def test_only_clock_module_reads_the_current_time():
    offenders = []
    assert CATALOG_DIR.is_dir()
    for path in CATALOG_DIR.rglob("*.py"):
        if path.name == "clock.py":
            continue
        source = path.read_text(encoding="utf-8")
        if any(forbidden in source for forbidden in FORBIDDEN):
            offenders.append(path.name)
    assert offenders == []


# ---------- Tests pour errors.py ----------


def test_tool_error_to_dict():
    error = ToolError("date_invalide", "La date est invalide.")
    assert error.to_dict() == {
        "ok": False,
        "error": {
            "code": "date_invalide",
            "message": "La date est invalide.",
            "details": {},
        },
    }


def test_tool_error_keeps_details():
    details = {"champ": "date"}  # La donnée qu'on va lui donner
    error = ToolError("date_invalide", "La date est invalide.", details)  # On la passe à l'erreur
    assert error.to_dict()["error"]["details"] == details


def test_tool_error_details_not_shared():
    first = ToolError("Code 1", "Premier message")  # details vaut donc juste {}
    second = ToolError("Code 2", "Deuxième message")  # details vaut également juste {}
    assert first.details is not second.details  # Devraient être considéré comme deux dictionnaires distincts


def test_tool_error_is_an_exception():
    with pytest.raises(ToolError) as exc:
        raise ToolError("date_invalide", "La date est invalide.")
    assert isinstance(exc.value, Exception)
    assert str(exc.value) == "La date est invalide."


def test_ok_returns_values():
    assert ok(a=1, b=2) == {"ok": True, "a": 1, "b": 2}


def test_ok_without_values():
    assert ok() == {"ok": True}


def test_ok_rejects_positional_arguments():
    with pytest.raises(TypeError):  # Nous devrions avoir une erreur avec la prochaine ligne
        ok(1)


# ---------- Tests pour bounds.py ----------


def test_require_passes_when_true():
    assert require(True, "code", "message") is None


def test_require_raises_when_false():
    with pytest.raises(ToolError) as exc:
        require(False, "code", "message")  # On prépare ma condition si la première valeur est False
    assert exc.value.code == "code"
    assert exc.value.message == "message"


def test_bounds_constants():
    assert MAX_DATE_RANGE_YEARS == 200
    assert MAX_LIST_ITEMS == 1000
