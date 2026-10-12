from app.catalog.tools.errors import ToolError

MAX_DATE_RANGE_YEARS = 200
MAX_LIST_ITEMS = 1000


def require(condition: bool, code: str, message: str) -> None:
    """Lève ToolError si la condition est fausse."""
    if not condition:
        raise ToolError(code, message)
