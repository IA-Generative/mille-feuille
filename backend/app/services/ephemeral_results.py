"""Vues compactes d'un run éphémère : classification et entités par page.

Dérivées de `EphemeralRunOut` (dossier vivant ou résultat conservé), pour les routes
/api/ephemeral/classifications et /api/ephemeral/extractions : l'appelant n'a pas besoin du
dossier complet (captures, étapes, résumés...).
"""

from app.models.document_page import PredictionKind, PredictionSource
from app.models.dossier import DossierStatus
from app.schemas.ephemeral import (
    EphemeralBox,
    EphemeralClassificationOut,
    EphemeralClassifiedDocument,
    EphemeralClassifiedPage,
    EphemeralEntityResult,
    EphemeralExtractedDocument,
    EphemeralExtractedPage,
    EphemeralExtractionOut,
    EphemeralLabelResult,
    EphemeralRunOut,
    EphemeralRunSummary,
)


def _error(run: EphemeralRunOut) -> str | None:
    if run.status != DossierStatus.ECHEC:
        return None
    return next((s.output for s in run.execution_steps if s.status == "échec" and s.output), "Le run a échoué")


def to_classification_out(run: EphemeralRunOut) -> EphemeralClassificationOut:
    return EphemeralClassificationOut(
        run_id=run.id,
        status=run.status,
        error=_error(run),
        expires_at=run.expires_at,
        documents=[
            EphemeralClassifiedDocument(
                name=document.name,
                pages=[
                    EphemeralClassifiedPage(
                        page_number=page.page_number,
                        labels=[
                            EphemeralLabelResult(
                                prediction_id=p.id, name=p.name, confidence=p.confidence, source=p.source
                            )
                            for p in sorted(
                                page.predictions,
                                key=lambda p: (p.source != PredictionSource.TEXTUAL, -(p.confidence or 0)),
                            )
                            if p.kind == PredictionKind.LABEL
                        ],
                    )
                    for page in sorted(document.pages, key=lambda p: p.page_number)
                ],
            )
            for document in run.documents
        ],
    )


def to_extracted_pages(document) -> list[EphemeralExtractedPage]:
    """Pages d'un document avec, pour chacune, ses entités et leurs zones. Partagé par le résultat d'un run éphémère et
    par les extractions d'un dossier (GET /api/dossiers/{id}/extractions) : `document` est un document de dossier."""
    # Une entité peut s'étendre sur plusieurs pages : la prédiction apparaît sur chacune d'elles, on
    # regroupe ses pages (pour `pages`) à partir de l'id de prédiction.
    pages_of: dict = {}
    for page in document.pages:
        for prediction in page.predictions:
            pages_of.setdefault(prediction.id, []).append(page.page_number)
    return [
        EphemeralExtractedPage(
            page_number=page.page_number,
            page_id=page.id,
            has_screenshot=page.has_screenshot,
            entities=[
                EphemeralEntityResult(
                    prediction_id=p.id,
                    name=p.name,
                    value=p.value,
                    confidence=p.confidence,
                    source=p.source,
                    pages=sorted(pages_of[p.id]),
                    # Une entité multi-pages porte les zones de toutes ses pages : on ne garde ici que celles de cette
                    # page.
                    boxes=[
                        EphemeralBox(x_min=b.x_min, y_min=b.y_min, x_max=b.x_max, y_max=b.y_max)
                        for b in p.bounding_boxes
                        if b.document_page_id == page.id
                    ],
                )
                for p in sorted(page.predictions, key=lambda p: p.source != PredictionSource.TEXTUAL)
                if p.kind == PredictionKind.ENTITY
            ],
        )
        for page in sorted(document.pages, key=lambda p: p.page_number)
    ]


def to_extraction_out(run: EphemeralRunOut) -> EphemeralExtractionOut:
    return EphemeralExtractionOut(
        run_id=run.id,
        status=run.status,
        error=_error(run),
        expires_at=run.expires_at,
        documents=[
            EphemeralExtractedDocument(name=document.name, pages=to_extracted_pages(document))
            for document in run.documents
        ],
    )


def to_run_summary(run: EphemeralRunOut) -> EphemeralRunSummary:
    # Un run à une seule étape (flux C) porte son type dans le nom de son dossier ; ses deux étapes existent
    # toujours, elles ne permettent pas de le deviner.
    kind = (
        "classification"
        if run.name.startswith("Classification")
        else "extraction"
        if run.name.startswith("Extraction")
        else "analyse"
    )
    return EphemeralRunSummary(
        id=run.id,
        kind=kind,
        status=run.status,
        documents=[document.name for document in run.documents],
        persist=run.persist,
        created_at=run.created_at,
        ended_at=run.ended_at,
        expires_at=run.expires_at,
    )
