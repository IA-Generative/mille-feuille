"""La numérotation des sources d'une réponse du chat : **une seule suite** pour les pages du dossier et pour les sources
d'une base de connaissances externe.

Le modèle cite une source par son numéro (`[2]`), et l'interface renvoie ce numéro à la bonne carte. Le numéro est donné
au moment où l'outil renvoie la source au modèle, et ne change plus pendant l'exécution : un même passage trouvé deux
fois garde son numéro, quel que soit l'outil qui le renvoie."""


class SourceNumbering:
    def __init__(self) -> None:
        self._numbers: dict[str, int] = {}

    def number(self, key: str) -> int:
        """Le numéro de cette source (à partir de 1) ; il est attribué à la première demande."""
        if key not in self._numbers:
            self._numbers[key] = len(self._numbers) + 1
        return self._numbers[key]
