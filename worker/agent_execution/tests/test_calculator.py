import pytest

from app.catalog.tools.calculator import calculate
from app.catalog.tools.errors import ToolError


def result(expression: str) -> str:
    return calculate(expression)["resultat"]


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1 + 2 * 3", "7"),
        ("(1 + 2) * 3", "9"),
        ("10 / 4", "2.5"),
        ("7 // 2", "3"),
        ("2 ** 10", "1024"),
        ("-(3 + 4) * 2", "-14"),
        ("max(3, 7, 5)", "7"),
        ("min(3, 7, 5)", "3"),
        ("abs(-4.5)", "4.5"),
        ("round(100 / 3, 2)", "33.33"),
        ("round(2.345, 2)", "2.35"),
    ],
)
def test_arithmetic(expression: str, expected: str) -> None:
    assert result(expression) == expected


def test_decimal_arithmetic_is_exact() -> None:
    """0,1 + 0,2 vaut exactement 0,3 : on calcule en décimal, pas en flottant."""
    assert result("0.1 + 0.2") == "0.3"


def test_french_number_formats_are_understood() -> None:
    assert result("1 234,50 * 1,2") == "1481.4"
    assert result("1 234 567,89 + 1") == "1234568.89"


def test_a_comma_inside_a_function_call_separates_the_arguments() -> None:
    assert result("round(1234, 1)") == "1234"
    assert result("max(3,7)") == "7"  # pas 3,7


def test_spaces_are_only_thousands_separators_in_groups_of_three_digits() -> None:
    with pytest.raises(ToolError) as error:
        calculate("3 7")
    assert error.value.code == "expression_invalide"


def test_the_result_comes_with_a_two_decimal_rounding_for_amounts() -> None:
    answer = calculate("100 / 3")
    assert (answer["resultat"], answer["arrondi_2_decimales"]) == ("33.33333333333333333333333333", "33.33")


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('id')",
        "open('/etc/passwd')",
        "(lambda: 1)()",
        "[1, 2]",
        "'a' * 3",
        "x + 1",
        "1 if True else 2",
        "().__class__",
        "[].__len__()",
        "eval('1')",
        "exec('1')",
    ],
)
def test_nothing_but_arithmetic_is_accepted(expression: str) -> None:
    with pytest.raises(ToolError) as error:
        calculate(expression)
    assert error.value.code in {"expression_invalide", "fonction_inconnue"}


@pytest.mark.parametrize(
    ("expression", "code"),
    [
        ("1 / 0", "division_par_zero"),
        ("1 // 0", "division_par_zero"),
        ("2 ** 1000", "calcul_trop_grand"),
        ("9 ** 9 ** 9", "calcul_trop_grand"),
        ("10 ** 31", "calcul_trop_grand"),
        ("2 ** 0.5", "puissance_invalide"),
        ("", "expression_vide"),
        ("   ", "expression_vide"),
        ("(1 + 2", "expression_invalide"),
        ("1 + " * 100 + "1", "expression_trop_longue"),
        ("1" * 201, "expression_trop_longue"),
        ("round(1, 2, 3)", "expression_invalide"),
        ("round(1, 11)", "expression_invalide"),
        ("max()", "expression_invalide"),
    ],
)
def test_errors_have_a_stable_code(expression: str, code: str) -> None:
    with pytest.raises(ToolError) as error:
        calculate(expression)
    assert error.value.code == code


def test_a_huge_expression_is_refused_before_it_is_evaluated() -> None:
    with pytest.raises(ToolError) as error:
        calculate("+".join(["1"] * 80))
    assert error.value.code == "expression_trop_longue"
