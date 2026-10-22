"""Les tools internes de la plateforme. Ils vivent dans le code, pas en base. **Ne sont proposés que ceux que le worker
sait exécuter pour un agent** (`implemented`) : les autres existent ici mais ne s'ajoutent pas.

Les identifiants sont stables (un agent y fait référence). Un agent qui garde un identifiant retiré ou pas encore
exécutable (`recherche_web`, `base_connaissances`…) le voit signalé comme indisponible et peut le retirer.

Les **outils de lecture du dossier** (recherche, lecture d'une page, classifications, entités) ne sont pas dans ce
catalogue : le worker les donne toujours à un agent, ils ne se choisissent pas."""

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
    # Le worker sait l'exécuter pour un agent. Faux : le tool existe mais n'est pas encore proposé.
    implemented: bool = False


INTERNAL_TOOLS: tuple[InternalTool, ...] = (
    InternalTool(
        "calculatrice",
        "Calculatrice",
        "Effectue des calculs exacts : montants, taux, totaux, pourcentages.",
        implemented=True,
    ),
    InternalTool(
        "calcul_dates",
        "Calcul de dates",
        "Jour de la semaine, ajout d'une durée, écart entre deux dates, bornes d'un mois ou d'un trimestre, "
        "date du jour.",
        implemented=True,
    ),
    InternalTool(
        "base_connaissances",
        "Base de connaissances",
        "Cherche dans les collections de la base de connaissances choisies pour l'analyse, avec les droits de la "
        "personne.",
        config="collections",
        implemented=True,
    ),
    # Pas encore exécutables : ils reviennent avec leur issue (chat des dossiers…).
    InternalTool("appel_agent", "Appel à un autre agent", "Délègue une sous-tâche à un autre agent de l'analyse."),
    InternalTool(
        "verification_coherence",
        "Vérification de cohérence",
        "Compare des informations entre documents et signale les écarts.",
    ),
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


def available_internal_tools() -> list[InternalTool]:
    """Ce qu'on peut proposer et ajouter à un agent aujourd'hui."""
    return [tool for tool in INTERNAL_TOOLS if tool.implemented]


def is_available(tool_id: str) -> bool:
    tool = get_internal_tool(tool_id)
    return tool is not None and tool.implemented
