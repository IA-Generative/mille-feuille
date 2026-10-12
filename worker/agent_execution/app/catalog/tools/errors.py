class ToolError(Exception):
    """Erreur d'un tool, au format que l'agent comprend."""

    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"ok": False, "error": {"code": self.code, "message": self.message, "details": self.details}}


def ok(**valeurs) -> dict:
    """Réponse de succès : ok=True plus les valeurs nommées."""
    return {"ok": True, **valeurs}
