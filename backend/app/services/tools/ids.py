from collections.abc import Sequence


def unique(tool_ids: Sequence[str]) -> list[str]:
    """Les identifiants sans doublon, dans l'ordre donné."""
    return list(dict.fromkeys(tool_ids))
