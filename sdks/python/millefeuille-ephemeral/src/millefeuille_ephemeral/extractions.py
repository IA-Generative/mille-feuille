from __future__ import annotations

import json
from collections.abc import Sequence

from millefeuille._files import FileInput
from millefeuille.models import EntityDefinitionIn

from millefeuille_ephemeral._oneshot import OneShotResource
from millefeuille_ephemeral.models import EphemeralExtraction


class EphemeralExtractionsResource(OneShotResource[EphemeralExtraction]):
    """Ressource `/api/ephemeral/extractions` : extraire les entités d'**un** document, sans définir d'analyse."""

    _path = "/ephemeral/extractions"
    _model = EphemeralExtraction

    def create(
        self,
        file: FileInput,
        entities: Sequence[EntityDefinitionIn | dict[str, str]],
        *,
        prompt: str = "",
        persist: bool = False,
        ttl_hours: int | None = None,
    ) -> EphemeralExtraction:
        """Crée le run et le lance. `entities` : au moins une entité (`name`, `definition`, `type`). Chaque document
        reçoit deux extractions : `textual` (LLM) et `gliner` (GLiNER2.5)."""
        definitions = [EntityDefinitionIn.model_validate(entity) for entity in entities]
        if not definitions:
            raise ValueError("Au moins une entité est requise.")
        data = {
            "entities": json.dumps([entity.model_dump(mode="json") for entity in definitions]),
            "extraction_prompt": prompt,
            "persist": persist,
        }
        return self._create(file, data, ttl_hours)
