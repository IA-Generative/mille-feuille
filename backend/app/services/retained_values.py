"""Les valeurs retenues de l'analyse courante des dossiers, lues par la recherche et les liens (#642, #643)."""

from collections.abc import Collection
from typing import Any

from sqlalchemy import ColumnElement, Select, func, literal_column, select
from sqlalchemy.orm import aliased

from app.models.document_page import PredictionValidationStatus
from app.models.dossier import Dossier
from app.models.dossier_analysis import AnalysisElement, AnalysisElementKind, AnalysisElementVersion, DossierAnalysis


def value_text() -> ColumnElement[str]:
    """La valeur d'un élément, en texte. Doit rester identique à l'expression de son index plein texte."""
    value = AnalysisElementVersion.value
    return func.coalesce(value.op("->>")(literal_column("'value'")), value.op("->>")(literal_column("'label'")))


def retained_values(kinds: Collection[AnalysisElementKind], *columns: Any) -> Select:
    """Les valeurs retenues de l'analyse courante de chaque dossier : la correction d'un instructeur prime, une valeur
    rejetée ne compte pas."""
    latest = aliased(DossierAnalysis)
    return (
        select(*columns)
        .select_from(AnalysisElementVersion)
        .join(AnalysisElement, AnalysisElement.retained_version_id == AnalysisElementVersion.id)
        .join(DossierAnalysis, DossierAnalysis.id == AnalysisElement.analysis_id)
        .join(Dossier, Dossier.id == DossierAnalysis.dossier_id)
        .where(
            AnalysisElement.kind.in_(kinds),
            AnalysisElementVersion.validation_status.is_distinct_from(PredictionValidationStatus.REJECTED.value),
            DossierAnalysis.sequence
            == select(func.max(latest.sequence)).where(latest.dossier_id == Dossier.id).scalar_subquery(),
        )
    )
