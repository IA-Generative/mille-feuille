"""Quelle permission demande une écriture, d'après sa route. **Tout ce qui n'est pas listé demande « modifier »** (un
dossier) ou « configurer » (une analyse) : une route ajoutée plus tard est protégée sans qu'on y pense."""

import re

from app.services.permissions import Permission

# Chemin après `/dossiers/{id}` : (méthodes, motif, permission). Le premier motif qui correspond gagne.
# `None` : voir le dossier suffit (conversations avec l'assistant, créneau personnel, présence).
_DOSSIER_RULES: list[tuple[set[str] | None, str, Permission | None]] = [
    ({"DELETE"}, r"^$", Permission.DOSSIER_DELETE),
    (None, r"^/(conversations(/.*)?|slot|analyses-dossier/[^/]+/presence)$", None),
    (None, r"/(validations|validate|reject|accept|modify|revisions)$", Permission.DOSSIER_VALIDATE),
    (None, r"^/(launch|stop|summary|suggest-analysis|question-answers/regenerate)$", Permission.DOSSIER_RUN),
    (None, r"^/documents/[^/]+/summary$", Permission.DOSSIER_RUN),
    (None, r"^/search-index/", Permission.DOSSIER_RUN),
    (None, r"^/document-drafts(/.*)?$", Permission.DOSSIER_GENERATE),
]


def for_dossier(method: str, suffix: str) -> Permission | None:
    for methods, pattern, permission in _DOSSIER_RULES:
        if (methods is None or method in methods) and re.search(pattern, suffix):
            return permission
    return Permission.DOSSIER_EDIT


def for_analyse(suffix: str) -> Permission | None:
    """Chemin après `/analyses/{id}`. `None` : la route décide elle-même (les accès, `routers/analyse_access.py`)."""
    if suffix.startswith("/access"):
        return None
    if suffix.startswith("/shares"):
        return Permission.ANALYSE_ACCESS
    return Permission.ANALYSE_CONFIGURE
