"""Vues compactes d'un run éphémère : classification et entités par page.

Dérivées de `EphemeralRunOut` (dossier vivant ou résultat conservé), pour les routes
/api/ephemeral/classifications et /api/ephemeral/extractions : l'appelant n'a pas besoin du
dossier complet (captures, étapes, résumés...).
"""

from app.models.document_page import PredictionKind, PredictionSource
from app.models.dossier import DossierStatus
from app.schemas.ephemeral import (
    EphemeralClassificationOut,
    EphemeralClassifiedDocument,
    EphemeralClassifiedPage,
    EphemeralEntityResult,
    EphemeralExtractedDocument,
    EphemeralExtractedPage,
    EphemeralExtractionOut,
    EphemeralLabelResult,
    EphemeralRunOut,
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
                            EphemeralLabelResult(name=p.name, confidence=p.confidence, source=p.source)
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


def to_extraction_out(run: EphemeralRunOut) -> EphemeralExtractionOut:
    documents = []
    for document in run.documents:
        # Une entité peut s'étendre sur plusieurs pages : la prédiction apparaît sur chacune d'elles, on
        # regroupe ses pages (pour `pages`) à partir de l'id de prédiction.
        pages_of: dict = {}
        for page in document.pages:
            for prediction in page.predictions:
                pages_of.setdefault(prediction.id, []).append(page.page_number)
        documents.append(
            EphemeralExtractedDocument(
                name=document.name,
                pages=[
                    EphemeralExtractedPage(
                        page_number=page.page_number,
                        entities=[
                            EphemeralEntityResult(
                                name=p.name,
                                value=p.value,
                                confidence=p.confidence,
                                source=p.source,
                                pages=sorted(pages_of[p.id]),
                            )
                            for p in sorted(page.predictions, key=lambda p: p.source != PredictionSource.TEXTUAL)
                            if p.kind == PredictionKind.ENTITY
                        ],
                    )
                    for page in sorted(document.pages, key=lambda p: p.page_number)
                ],
            )
        )
    return EphemeralExtractionOut(
        run_id=run.id, status=run.status, error=_error(run), expires_at=run.expires_at, documents=documents
    )
