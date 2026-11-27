"""Permissions des rôles de l'application (issue #659) : une liste fixe, dont chaque rôle est un sous-ensemble.

Le modèle seulement : les droits réels restent ceux de Keycloak jusqu'à l'issue #660."""

import enum
import uuid


class Permission(enum.StrEnum):
    DOSSIER_VIEW = "dossier.view"
    DOSSIER_EDIT = "dossier.edit"
    DOSSIER_RUN = "dossier.run"
    DOSSIER_VALIDATE = "dossier.validate"
    DOSSIER_GENERATE = "dossier.generate"
    DOSSIER_DELETE = "dossier.delete"
    ANALYSE_CREATE = "analyse.create"
    ANALYSE_CONFIGURE = "analyse.configure"
    ANALYSE_ACCESS = "analyse.access"
    GROUP_MEMBERS = "group.members"


# Rôles créés par la migration. Seul « Admin de groupe » est figé.
GROUP_ADMIN_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
INSTRUCTOR_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")
READER_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")
