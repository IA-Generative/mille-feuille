"""Découpage de l'extraction d'entités (issue #126, parent #113).

Fonctions pures (pas d'appel réseau ni au LLM) :

- les définitions d'entités sont réparties en **groupes de taille fixe** ;
- les pages d'un **document** sont réparties en **lots** dont la taille est
  définie par un **budget de jetons**, avec un recouvrement entre lots
  consécutifs pour ne pas couper une entité qui s'étend sur deux lots ;
- les entités en double dues au recouvrement sont écartées.

Une unité de calcul = un lot de pages × un groupe de définitions.

Les jetons sont **estimés** (un jeton ≈ 4 caractères) : pas de dépendance à un
tokenizer, donc une approximation. Les seuils sont des réglages à ajuster sur
de vrais dossiers.
"""

from collections.abc import Iterable

_CHARS_PER_TOKEN = 4
# Texte minimal d'un lot même si les définitions et le prompt sont volumineux.
_MIN_TEXT_BUDGET = 500
# Mise en forme du texte des pages dans la requête ("--- Page N ---\n...").
_PAGE_OVERHEAD_TOKENS = 8
# Instruction système fixe ajoutée par llm.extract_entities_batch.
_SYSTEM_OVERHEAD_TOKENS = 120


def estimate_tokens(text: str | None) -> int:
    """Estimation grossière du nombre de jetons d'un texte."""
    return max(1, (len(text or "") + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def group_definitions(definitions: list[dict], size: int) -> list[list[dict]]:
    """Groupes de taille fixe, dans l'ordre de l'analyse. Ajouter une définition
    à la fin ne change que le dernier groupe ; en insérer une au milieu décale
    les suivants. ``size`` <= 0 : un seul groupe avec toutes les définitions."""
    if not definitions:
        return []
    if size <= 0:
        return [list(definitions)]
    return [definitions[i : i + size] for i in range(0, len(definitions), size)]


def text_budget(*, max_tokens: int, reserved_output_tokens: int, prompt: str, definitions: list[dict]) -> int:
    """Jetons disponibles pour le texte des pages d'un lot : le budget total
    moins la réponse attendue, le prompt, les définitions du groupe et
    l'instruction fixe."""
    definitions_text = "\n".join(
        f"- {d.get('name')} (type: {d.get('type')}): {d.get('definition')}" for d in definitions
    )
    overhead = _SYSTEM_OVERHEAD_TOKENS + estimate_tokens(prompt) + estimate_tokens(definitions_text)
    return max(_MIN_TEXT_BUDGET, max_tokens - reserved_output_tokens - overhead)


def plan_lots(pages: list[dict], *, budget: int, overlap: int) -> list[list[dict]]:
    """Lots de pages consécutives d'un même document.

    Un lot s'arrête quand la page suivante ferait dépasser le budget ; le lot
    suivant reprend ``overlap`` page(s) avant la fin du précédent. Une page à
    elle seule plus grande que le budget forme son propre lot (on ne la coupe
    pas). Un document qui tient dans le budget donne un seul lot."""
    if not pages:
        return []
    costs = [estimate_tokens(page.get("content")) + _PAGE_OVERHEAD_TOKENS for page in pages]
    lots: list[list[dict]] = []
    start = 0
    while start < len(pages):
        end = start
        used = 0
        while end < len(pages) and (end == start or used + costs[end] <= budget):
            used += costs[end]
            end += 1
        lots.append(pages[start:end])
        if end >= len(pages):
            break
        # Recouvrement, sans jamais reculer jusqu'au début du lot : on avance toujours.
        start = max(start + 1, end - max(0, overlap))
    return lots


def normalize_value(value: str | None) -> str:
    """Forme comparable d'une valeur : casse et espaces ignorés."""
    return " ".join((value or "").lower().split())


def new_entities(entities: Iterable, seen: set[tuple[str, str]]) -> list:
    """Entités d'un lot qui ne figurent pas déjà parmi celles des lots
    précédents du même document et du même groupe (même définition, même
    valeur). ``seen`` est mis à jour. Sert à fusionner les doublons dus au
    recouvrement."""
    kept = []
    for entity in entities:
        key = (entity.entity_name, normalize_value(entity.value))
        if key in seen:
            continue
        seen.add(key)
        kept.append(entity)
    return kept
