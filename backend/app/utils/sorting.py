import unicodedata


def sort_key(text: str) -> str:
    """Ordre alphabétique sans casse ni accents (« É » avec « E »), pour trier en Python."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))
