from app.models.analyse import Analyse
from app.schemas.dossier import (
    InternalAgentOut,
    InternalAnalyseOut,
    InternalClassificationOut,
    InternalEntityDefinitionOut,
    InternalExtractionOut,
    InternalKnowledgeCollectionOut,
    InternalLabelDefinitionOut,
)


def build_internal_analyse(analyse: Analyse) -> InternalAnalyseOut:
    """Les définitions d'une analyse telles que les travaux les lisent : labels, entités, agents, collections."""
    return InternalAnalyseOut(
        id=analyse.id,
        classification=InternalClassificationOut(
            prompt=analyse.classification_prompt,
            multi_label=analyse.multi_label,
            labels=[InternalLabelDefinitionOut.model_validate(label) for label in analyse.labels],
        ),
        extraction=InternalExtractionOut(
            prompt=analyse.extraction_prompt,
            entities=[InternalEntityDefinitionOut.model_validate(entity) for entity in analyse.entities],
        ),
        agents=[InternalAgentOut.model_validate(agent) for agent in analyse.agents],
        knowledge_collections=[
            InternalKnowledgeCollectionOut.model_validate(item) for item in analyse.knowledge_collections
        ],
    )
