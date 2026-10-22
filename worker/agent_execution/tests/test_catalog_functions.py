import json

import pytest

from app.catalog.functions import FUNCTIONS_BY_TOOL, CatalogFunction

ALL = {function.name: function for functions in FUNCTIONS_BY_TOOL.values() for function in functions}


def run(name: str, **arguments) -> dict:
    return json.loads(ALL[name].run(arguments))


def test_the_worker_runs_exactly_the_tools_the_backend_offers() -> None:
    assert set(FUNCTIONS_BY_TOOL) == {"calculatrice", "calcul_dates"}


def test_function_names_are_unique_and_valid_for_the_model() -> None:
    names = [function.name for functions in FUNCTIONS_BY_TOOL.values() for function in functions]
    assert len(names) == len(set(names))
    assert all(name.replace("_", "").isalnum() and len(name) <= 64 for name in names)


@pytest.mark.parametrize("function", list(ALL.values()), ids=list(ALL))
def test_every_definition_is_a_valid_function_calling_schema(function: CatalogFunction) -> None:
    definition = function.definition()["function"]
    assert definition["description"]
    parameters = definition["parameters"]
    assert parameters["type"] == "object"
    assert set(parameters["required"]) <= set(parameters["properties"])
    assert all("description" in prop for prop in parameters["properties"].values())


def test_dates() -> None:
    assert run("jour_de_la_semaine", date="2026-03-03")["jour"] == "mardi"
    assert run("ajouter_une_duree", date="2026-01-31", mois=1)["date"] == "2026-02-28"  # fin de mois
    assert run("ajouter_une_duree", date="2026-03-03", jours=-3)["date"] == "2026-02-28"
    assert run("ecart_entre_dates", debut="1990-05-12", fin="2026-03-03")["libelle"] == "35 ans, 9 mois et 19 jours"
    assert run("ecart_en_jours", debut="2026-01-01", fin="2026-01-15")["jours"] == 14
    assert run("bornes_du_mois", date="2026-02-10") == {"ok": True, "debut": "2026-02-01", "fin": "2026-02-28"}
    assert run("bornes_du_trimestre", date="2026-05-20")["trimestre"] == 2
    assert run("semaine_iso", date="2026-03-03")["semaine"] == 10
    assert run("comparer_dates", a="2026-03-03", b="2026-03-10") == {
        "ok": True,
        "relation": "avant",
        "jours_d_ecart": 7,
    }
    assert run("date_dans_la_periode", date="2026-03-03", debut="2026-01-01", fin="2026-12-31")["dans_la_periode"]
    assert not run("date_dans_la_periode", date="2026-01-01", debut="2026-01-01", fin="2026-12-31", inclusif=False)[
        "dans_la_periode"
    ]


def test_today_comes_from_the_system_clock() -> None:
    answer = run("date_et_heure_actuelles")
    assert answer["ok"] and len(answer["date"]) == 10
    assert run("date_et_heure_actuelles", fuseau="Pacific/Noumea")["iso"].endswith("+11:00")


def test_the_calculator_function() -> None:
    assert run("calculer", expression="round(1234.5 * 1.2, 2)")["resultat"] == "1481.4"


def test_a_tool_error_is_returned_as_json_for_the_model_never_raised() -> None:
    answer = run("jour_de_la_semaine", date="31/02/2026")
    assert answer["ok"] is False and answer["error"]["code"] == "date_invalide"
    assert run("calculer", expression="1/0")["error"]["code"] == "division_par_zero"


def test_wrong_arguments_say_what_is_expected() -> None:
    answer = run("jour_de_la_semaine", jour="2026-03-03")
    assert answer["error"]["code"] == "arguments_invalides"
    assert "date" in answer["error"]["message"]
    assert run("jour_de_la_semaine")["error"]["code"] == "arguments_invalides"
