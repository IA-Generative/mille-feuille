"""Le résultat d'un appel de tool, tel que le worker (et le modèle) le reçoivent : jamais d'exception, un code stable
et un message en français. La sortie d'un serveur MCP tiers est **non fiable** (risque d'injection dans le prompt) :
elle est toujours marquée comme telle et bornée en taille."""

from dataclasses import dataclass

# Les messages que le modèle lit. Un code inconnu (venant de `credentials`) garde son propre message.
MESSAGES = {
    "outil_interne": "Cet outil est interne : il est exécuté par la plateforme, pas par un serveur MCP.",
    "outil_inconnu": "Cet outil n'existe pas.",
    "outil_desactive": "Cet outil n'est pas autorisé par la personne qui a ajouté le serveur.",
    "adresse_refusee": "L'adresse du serveur n'est plus autorisée.",
    "quota_depasse": "Trop d'appels d'outils : réessayez dans quelques instants.",
    "arguments_trop_longs": "Les arguments de l'appel sont trop volumineux.",
    "delai_depasse": "Le serveur n'a pas répondu à temps.",
    "serveur_indisponible": "Le serveur de cet outil est indisponible.",
    "outil_en_erreur": "L'outil a répondu par une erreur.",
}


@dataclass(frozen=True)
class ToolCallOutcome:
    ok: bool
    output: str = ""
    code: str | None = None
    truncated: bool = False

    @classmethod
    def failure(cls, code: str, message: str | None = None) -> "ToolCallOutcome":
        return cls(ok=False, code=code, output=message or MESSAGES.get(code, "L'appel a échoué."))


def bound_output(text: str, max_chars: int) -> tuple[str, bool]:
    """Coupe la sortie à `max_chars` caractères ; renvoie le texte et s'il a été coupé."""
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True
