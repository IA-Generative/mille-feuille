"""Dans quels labels de classification chaque page d'un dossier est-elle classée ?

Sert à limiter une entité aux pages d'un label (`EntityDefinition.label_id`). C'est la **valeur retenue** de la
classification qui fait foi : si un instructeur a corrigé le label d'une page, c'est le sien, et une classification
qu'il a rejetée ne compte pas. À défaut d'élément d'analyse (analyse absente, élément non créé), on lit les
prédictions déposées par le worker.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.analyse import LabelDefinition
from app.models.document_page import DocumentPage, DocumentPrediction, PredictionKind
from app.models.dossier import DossierDocument
from app.models.dossier_analysis import AnalysisElement, AnalysisElementKind, AnalysisElementVersion
from app.repositories.dossier_analysis_repository import DossierAnalysisRepository

REJECTED = "rejeté"


async def page_label_ids(
    db: AsyncSession, dossier_id: uuid.UUID, analyse_id: uuid.UUID
) -> dict[uuid.UUID, set[uuid.UUID]]:
    """Pour chaque page classée du dossier, les identifiants des labels dans lesquels elle l'est (plusieurs en
    classification multi-label). Une page sans classification n'apparaît pas."""
    labels = (await db.execute(select(LabelDefinition).where(LabelDefinition.analyse_id == analyse_id))).scalars().all()
    by_id = {label.id: label.id for label in labels}
    by_name = {label.name.casefold(): label.id for label in labels}

    pages = await db.execute(
        select(DocumentPage.id, DocumentPage.dossier_document_id, DocumentPage.page_number)
        .join(DossierDocument, DossierDocument.id == DocumentPage.dossier_document_id)
        .where(DossierDocument.dossier_id == dossier_id)
    )
    page_by_position = {(document_id, number): page_id for page_id, document_id, number in pages.all()}
    page_ids = set(page_by_position.values())

    result: dict[uuid.UUID, set[uuid.UUID]] = {}
    covered: set[uuid.UUID] = set()

    analysis = await DossierAnalysisRepository(db).get_current(dossier_id)
    if analysis is not None:
        rows = await db.execute(
            select(AnalysisElement, AnalysisElementVersion)
            .join(AnalysisElementVersion, AnalysisElementVersion.id == AnalysisElement.retained_version_id)
            .where(
                AnalysisElement.analysis_id == analysis.id, AnalysisElement.kind == AnalysisElementKind.CLASSIFICATION
            )
        )
        for element, version in rows.all():
            page_id = page_by_position.get((element.document_id, element.first_page_number))
            if page_id is None:
                continue
            covered.add(page_id)
            if version.validation_status == REJECTED:
                continue
            name = str((version.value or {}).get("label", "")).casefold()
            # Une valeur corrigée par un instructeur porte le nom du label : on la lit avant l'identifiant d'origine.
            label_id = by_name.get(name) or by_id.get(element.definition_id)
            if label_id is not None:
                result.setdefault(page_id, set()).add(label_id)

    predictions = await db.execute(
        select(DocumentPrediction)
        .options(selectinload(DocumentPrediction.pages))
        .where(
            DocumentPrediction.kind == PredictionKind.LABEL,
            DocumentPrediction.label_definition_id.in_(list(by_id)),
        )
    )
    for prediction in predictions.scalars().all():
        for page in prediction.pages:
            if page.id in covered or page.id not in page_ids:
                continue
            result.setdefault(page.id, set()).add(prediction.label_definition_id)
    return result
