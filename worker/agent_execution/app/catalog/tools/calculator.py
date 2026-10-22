"""Calculatrice : évalue une expression arithmétique **sans jamais exécuter de code**. On lit l'expression avec `ast`,
on n'accepte qu'une liste blanche de nœuds, et on calcule en décimal (0,1 + 0,2 donne exactement 0,3).

Accepté : nombres, `+ - * / // **`, parenthèses, signe, et `round`, `abs`, `min`, `max`. La virgule décimale et les
espaces des milliers (« 1 234,50 ») sont acceptés. Tout le reste est refusé."""

import ast
import operator
import re
from decimal import ROUND_HALF_UP, Decimal, DivisionByZero, InvalidOperation
from typing import Any

from app.catalog.tools.bounds import require
from app.catalog.tools.errors import ToolError, ok

MAX_EXPRESSION_CHARS = 200
MAX_NODES = 100
MAX_EXPONENT = 100
MAX_ABS_RESULT = Decimal(10) ** 30

BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
}
FUNCTIONS = {"round", "abs", "min", "max"}


def _normalize(expression: str) -> str:
    """« 1 234,50 » devient « 1234.50 ». Les espaces ne sont retirés que comme séparateur de milliers (groupes de
    trois chiffres), et la virgule n'est décimale que **hors d'un appel de fonction** : dans `round(x, 2)` elle sépare
    les arguments, et les décimales s'y écrivent avec un point."""
    text = re.sub(r"(?<=\d)[ \u00a0\u202f](?=\d{3}(?!\d))", "", expression)
    out: list[str] = []
    in_call: list[bool] = []  # une entrée par parenthèse ouverte : est-ce l'appel d'une fonction ?
    for i, char in enumerate(text):
        if char == "(":
            in_call.append(bool(re.search(r"[A-Za-z_]\s*$", text[:i])))
        elif char == ")" and in_call:
            in_call.pop()
        elif (
            char == ","
            and not any(in_call)
            and 0 < i < len(text) - 1
            and text[i - 1].isdigit()
            and text[i + 1].isdigit()
        ):
            char = "."
        out.append(char)
    return "".join(out)


def _too_big(value: Decimal) -> None:
    require(abs(value) <= MAX_ABS_RESULT, "calcul_trop_grand", "Le résultat est trop grand pour être calculé.")


def _power(base: Decimal, exponent: Decimal) -> Decimal:
    require(exponent == exponent.to_integral_value(), "puissance_invalide", "L'exposant doit être un nombre entier.")
    require(abs(exponent) <= MAX_EXPONENT, "calcul_trop_grand", f"L'exposant ne peut pas dépasser {MAX_EXPONENT}.")
    result = base ** int(exponent)
    _too_big(result)
    return result


class _Evaluator:
    def __init__(self, source: str) -> None:
        self.source = source

    def number(self, node: ast.Constant) -> Decimal:
        require(
            isinstance(node.value, int | float) and not isinstance(node.value, bool),
            "expression_invalide",
            "Seuls les nombres sont acceptés.",
        )
        # Le texte exact du nombre, pas le float : 0.1 reste 0.1.
        return Decimal(ast.get_source_segment(self.source, node) or str(node.value))

    def call(self, node: ast.Call) -> Decimal:
        name = node.func.id if isinstance(node.func, ast.Name) else ""
        require(
            name in FUNCTIONS and not node.keywords, "fonction_inconnue", f"Fonction non autorisée : {name or '?'}."
        )
        args = [self.visit(arg) for arg in node.args]
        require(bool(args), "expression_invalide", f"{name} demande au moins un nombre.")
        if name == "abs":
            require(len(args) == 1, "expression_invalide", "abs demande un seul nombre.")
            return abs(args[0])
        if name == "round":
            require(
                len(args) in (1, 2),
                "expression_invalide",
                "round demande un nombre et, au plus, le nombre de décimales.",
            )
            places = int(args[1]) if len(args) == 2 else 0
            require(0 <= places <= 10, "expression_invalide", "Le nombre de décimales doit être entre 0 et 10.")
            return args[0].quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
        return min(args) if name == "min" else max(args)

    def visit(self, node: ast.AST) -> Decimal:
        if isinstance(node, ast.Constant):
            return self.number(node)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
            value = self.visit(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            return _power(self.visit(node.left), self.visit(node.right))
        if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
            left, right = self.visit(node.left), self.visit(node.right)
            require(
                not (isinstance(node.op, ast.Div | ast.FloorDiv) and right == 0),
                "division_par_zero",
                "Division par zéro.",
            )
            result = BINARY[type(node.op)](left, right)
            _too_big(result)
            return result
        if isinstance(node, ast.Call):
            return self.call(node)
        raise ToolError("expression_invalide", "Cette expression n'est pas un calcul autorisé.")


def _format(value: Decimal) -> str:
    """Le nombre sans exposant ni zéros inutiles : 1E+2 devient 100, 2.50 devient 2.5."""
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def calculate(expression: str) -> dict[str, Any]:
    """Évalue l'expression ; renvoie le résultat exact et son arrondi à deux décimales (montants)."""
    require(isinstance(expression, str) and expression.strip() != "", "expression_vide", "L'expression est vide.")
    require(
        len(expression) <= MAX_EXPRESSION_CHARS,
        "expression_trop_longue",
        f"L'expression dépasse {MAX_EXPRESSION_CHARS} caractères.",
    )
    source = _normalize(expression.strip())
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as error:
        raise ToolError("expression_invalide", "L'expression n'est pas un calcul valide.") from error
    require(sum(1 for _ in ast.walk(tree)) <= MAX_NODES, "expression_trop_longue", "L'expression est trop complexe.")
    try:
        value = _Evaluator(source).visit(tree.body)
    except (InvalidOperation, DivisionByZero, OverflowError) as error:
        raise ToolError("calcul_impossible", "Le calcul n'a pas de résultat.") from error
    return ok(
        expression=expression.strip(),
        resultat=_format(value),
        arrondi_2_decimales=_format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
    )
