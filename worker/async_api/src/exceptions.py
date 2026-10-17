"""Erreurs fonctionnelles du worker, rendues au consommateur sous la forme `CODE: détail`.

Chaque erreur porte un ``error_code`` stable (SCREAMING_SNAKE_CASE), unique par sa sémantique
dans la plateforme async-api : un SI qui enchaîne plusieurs services matche une seule chaîne
(`FILE_TOO_LARGE` est le même code que chez office-convert ou ocr-classic). ``task.py`` attrape
ces exceptions et formate l'``error_message`` final en ``f"{error_code}: {detail}"`` ; une
erreur du backend mille-feuille est traduite en code neutre (garde C-17 : ni URL, ni code HTTP,
ni texte brut du serveur chez le consommateur — le détail part au journal) ; toute autre
exception est réemballée en ``WORKER_ERROR`` générique.
"""


class MilleFeuilleBridgeError(Exception):
    """Base des erreurs fonctionnelles : porte un error_code stable + un détail lisible."""

    error_code: str  # défini par chaque sous-classe

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class InvalidRequestError(MilleFeuilleBridgeError):
    """Message d'entrée non conforme au contrat, ou refusé par le service d'analyse (400/422)."""

    error_code = "INVALID_REQUEST"


class TooManyFilesError(MilleFeuilleBridgeError):
    """Plus de documents que la borne du worker (`MAX_FILES`)."""

    error_code = "TOO_MANY_FILES"


class FileTooLargeError(MilleFeuilleBridgeError):
    """Un fichier (ou leur total) dépasse la borne mémoire du worker — vérifié par HEAD, avant tout téléchargement."""

    error_code = "FILE_TOO_LARGE"


class FichierIntrouvableError(MilleFeuilleBridgeError):
    """Un `file_id` ne désigne aucun objet du stockage."""

    error_code = "FILE_NOT_FOUND"


class AnalysisNotFoundError(MilleFeuilleBridgeError):
    """`analyse_id` ne désigne aucune analyse visible du jeton du worker (404 du service d'analyse)."""

    error_code = "ANALYSIS_NOT_FOUND"


class RunFailedError(MilleFeuilleBridgeError):
    """Le run mille-feuille s'est terminé en `échec` ou `arrêté`."""

    error_code = "RUN_FAILED"


class RunTimeoutError(MilleFeuilleBridgeError):
    """Le run n'a pas atteint un état terminal dans le délai imparti."""

    error_code = "RUN_TIMEOUT"


class UpstreamError(MilleFeuilleBridgeError):
    """Le service d'analyse a répondu par une erreur qui n'est pas du ressort du consommateur
    (authentification du worker, 5xx, réseau) : réessayer plus tard."""

    error_code = "UPSTREAM_ERROR"


#: Libellé générique d'une panne technique du worker lui-même : le détail est au journal.
ECHEC_TECHNIQUE = "WORKER_ERROR: Le traitement a échoué pour une raison technique"
