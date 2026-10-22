"""Les tools internes de la plateforme. Ils vivent dans le code, pas en base : leur liste suit celle des outils que
le worker sait exécuter. Les identifiants sont stables (un agent y fait référence) ; les six premiers sont ceux de
l'ancienne énumération `AgentTool`, ce qui évite de migrer les agents existants."""

from dataclasses import dataclass


@dataclass(frozen=True)
class InternalTool:
    id: str
    name: str
    description: str
    # Le tool modifie des données : le chat demande une confirmation avant l'appel.
    side_effect: bool = False
    # Le tool demande une configuration par analyse (ex : les collections de la base de connaissances).
    config: str | None = None


INTERNAL_TOOLS: tuple[InternalTool, ...] = (
    InternalTool("lecture_document", "Lecture de document", "Lit le contenu d'un document du dossier, page par page."),
    InternalTool("recherche_web", "Recherche web", "Cherche une information sur le web."),
    InternalTool(
        "base_connaissances",
        "Base de connaissances",
        "Interroge la base de connaissances de la plateforme.",
        config="collections",
    ),
    InternalTool("appel_agent", "Appel à un autre agent", "Délègue une sous-tâche à un autre agent de l'analyse."),
    InternalTool("calculatrice", "Calculatrice", "Effectue des calculs exacts (montants, taux, totaux)."),
    InternalTool(
        "verification_coherence",
        "Vérification de cohérence",
        "Compare des informations entre documents et signale les écarts.",
    ),
    InternalTool(
        "recherche_dossier", "Recherche dans le dossier", "Cherche des passages dans les documents du dossier."
    ),
    InternalTool("calcul_dates", "Calcul de dates", "Délais, échéances et durées entre deux dates."),
    InternalTool("notes_internes", "Notes internes", "Ajoute une note interne au dossier.", side_effect=True),
    InternalTool(
        "propositions_analyse",
        "Propositions de modification de l'analyse",
        "Propose de modifier un élément de l'analyse, à valider par une personne.",
        side_effect=True,
    ),
)


def get_internal_tool(tool_id: str) -> InternalTool | None:
    return next((tool for tool in INTERNAL_TOOLS if tool.id == tool_id), None)
