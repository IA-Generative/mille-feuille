class CredentialsUnavailableError(Exception):
    """Le mode d'authentification du serveur n'est pas utilisable pour cet appel ; `code` est stable et lisible par une
    machine, `message` est en français et affichable à la personne comme au modèle."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
