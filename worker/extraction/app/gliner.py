"""Extraction d'entités avec GLiNER2.5 (CPU).

GLiNER extrait des empans de texte pour des types d'entités donnés **avec leur description** : on lui passe les
définitions de l'analyse (`nom -> définition`). C'est un petit modèle d'extraction, sans LLM : il complète
l'extraction par LLM avec des valeurs littéralement présentes dans le texte, chacune avec sa confiance.

Le modèle est chargé une fois par process, à la première page à traiter (quelques secondes). Un texte plus long que la
fenêtre du modèle est découpé en morceaux qui se recouvrent (`extract_entities_long`).
"""

import logging
import threading

from app.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_model = None

# GLiNER extrait des empans de texte : une entité de type booléen (« oui/non ») n'en est pas un.
UNSUPPORTED_TYPES = frozenset({"booléen"})


def _load():
    """Le modèle GLiNER, chargé une seule fois. L'import est différé : torch ne se charge pas tant que
    l'extraction GLiNER n'est pas demandée."""
    global _model
    with _lock:
        if _model is None:
            import torch
            from gliner2 import AutoExtractor

            torch.set_num_threads(settings.GLINER_NUM_THREADS)
            _model = AutoExtractor.from_pretrained(settings.GLINER_MODEL, map_location="cpu")
            logger.info("GLiNER model %s loaded on CPU", settings.GLINER_MODEL)
        return _model


ENTITE = "entité"
SEMANTIQUE = "sémantique"


def nature_of(entity_definition: dict) -> str:
    """Nature d'une définition (entité nommée ou sémantique) ; « entité » si le backend ne la donne pas."""
    return entity_definition.get("nature") or ENTITE


def supported(entity_definitions: list[dict]) -> list[dict]:
    """Les définitions que GLiNER traite : les entités nommées, d'un type qui est un empan de texte."""
    return [e for e in entity_definitions if nature_of(e) == ENTITE and e.get("type") not in UNSUPPORTED_TYPES]


def semantic(entity_definitions: list[dict], gliner_enabled: bool) -> list[dict]:
    """Les définitions que traite l'extraction sémantique (LLM) : les définitions sémantiques et les entités que
    GLiNER ne peut pas extraire (booléens, ou GLiNER désactivé) : elles ne resteraient sinon extraites par personne."""
    taken_by_gliner = {e["name"] for e in supported(entity_definitions)} if gliner_enabled else set()
    return [e for e in entity_definitions if e["name"] not in taken_by_gliner]


def entity_types(entity_definitions: list[dict]) -> dict[str, str]:
    """`nom -> description` passé à GLiNER : la définition de l'entité, ou son nom si elle n'en a pas."""
    return {e["name"]: (e.get("definition") or "").strip() or e["name"] for e in entity_definitions}


def extract(text: str, entity_definitions: list[dict]) -> list[tuple[str, str, float, int | None, int | None]]:
    """Entités trouvées dans `text` : (nom de la définition, valeur, confiance, début, fin), au-dessus de
    GLINER_THRESHOLD. Début et fin sont les offsets de la valeur dans `text` (None si GLiNER ne les donne pas).
    Les noms qui ne correspondent à aucune définition sont écartés."""
    types = entity_types(entity_definitions)
    if not text.strip() or not types:
        return []
    result = _load().extract_entities_long(
        text,
        types,
        threshold=settings.GLINER_THRESHOLD,
        include_confidence=True,
    )
    found = []
    for name, spans in result.get("entities", {}).items():
        if name not in types:
            continue
        for span in spans:
            raw = span.get("text") or ""
            value = raw.strip()
            if value:
                # Les offsets de GLiNER encadrent le texte brut : on les resserre sur la valeur sans ses espaces.
                start, end = span.get("start"), span.get("end")
                if start is not None and end is not None:
                    start += len(raw) - len(raw.lstrip())
                    end = start + len(value)
                found.append((name, value, float(span.get("confidence", 0.0)), start, end))
    return found
