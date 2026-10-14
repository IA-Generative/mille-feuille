from __future__ import annotations

import json
from collections.abc import Sequence

from millefeuille._files import FileInput
from millefeuille.models import LabelDefinitionIn

from millefeuille_ephemeral._oneshot import OneShotResource
from millefeuille_ephemeral.models import EphemeralClassification


class EphemeralClassificationsResource(OneShotResource[EphemeralClassification]):
    """Ressource `/api/ephemeral/classifications` : classer les pages d'**un** document, sans définir d'analyse."""

    _path = "/ephemeral/classifications"
    _model = EphemeralClassification

    def create(
        self,
        file: FileInput,
        labels: Sequence[LabelDefinitionIn | dict[str, str]],
        *,
        multi_label: bool = False,
        prompt: str = "",
        persist: bool = False,
        ttl_hours: int | None = None,
    ) -> EphemeralClassification:
        """Crée le run et le lance. `labels` : au moins une catégorie (`name`, `definition`). `multi_label=False` :
        un seul label par page ; `True` : un ou plusieurs. Chaque page reçoit deux classifications : `textual` et
        `visual`."""
        definitions = [LabelDefinitionIn.model_validate(label) for label in labels]
        if not definitions:
            raise ValueError("Au moins une catégorie est requise.")
        data = {
            "labels": json.dumps([label.model_dump(mode="json") for label in definitions]),
            "multi_label": multi_label,
            "classification_prompt": prompt,
            "persist": persist,
        }
        return self._create(file, data, ttl_hours)
