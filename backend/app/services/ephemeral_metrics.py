"""Condensé non sensible d'un run éphémère et métriques calculées dessus et sur les verdicts des appelants.

Rien ici ne lit ni ne garde le contenu des documents ni les valeurs extraites : voir `EphemeralRunMetrics`."""

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from app.models.document_page import PredictionKind, PredictionSource
from app.models.ephemeral_feedback import EphemeralFeedback, EphemeralVerdict
from app.models.ephemeral_run_metrics import EphemeralRunMetrics
from app.schemas.dossier import DossierOut
from app.schemas.ephemeral_metrics import (
    AgreementOut,
    ConfusionOut,
    GlobalMetricsOut,
    NameQualityOut,
    NameVolumeOut,
    QualityOut,
    RunMetricsOut,
    SourceQualityOut,
    StepMetricsOut,
    VolumeOut,
)


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _seconds(start, end) -> float | None:
    return round((end - start).total_seconds(), 3) if start is not None and end is not None else None


def build_digest(run: DossierOut) -> dict[str, Any]:
    """Les champs de `EphemeralRunMetrics` pour un run (dossier vivant ou instantané) : uniquement des données non
    sensibles. Une entité sur plusieurs pages est une seule prédiction, rattachée à sa première page."""
    predictions: dict[uuid.UUID, dict[str, Any]] = {}
    page_count = 0
    for document_index, document in enumerate(run.documents):
        for page in document.pages:
            page_count += 1
            for prediction in page.predictions:
                entry = predictions.setdefault(
                    prediction.id,
                    {
                        "id": str(prediction.id),
                        "kind": prediction.kind.value,
                        "name": prediction.name,
                        "source": prediction.source.value,
                        "confidence": prediction.confidence,
                        # Les numéros de page sont propres à chaque document : on garde son rang (jamais son nom).
                        "document": document_index,
                        "page_number": page.page_number,
                    },
                )
                entry["page_number"] = min(entry["page_number"], page.page_number)
    return {
        "status": run.status.value,
        "document_count": len(run.documents),
        "page_count": page_count,
        "duration_seconds": _seconds(run.started_at, run.ended_at),
        "steps": [
            {
                "kind": step.kind.value,
                "status": step.status.value,
                "duration_seconds": _seconds(step.started_at, step.ended_at),
            }
            for step in run.execution_steps
        ],
        "predictions": sorted(
            predictions.values(), key=lambda p: (p["page_number"], p["kind"], p["name"], p["source"])
        ),
    }


def _quality(rows: Iterable[EphemeralFeedback]) -> dict[str, Any]:
    rows = list(rows)
    correct = [r for r in rows if r.verdict == EphemeralVerdict.CORRECT]
    incorrect = [r for r in rows if r.verdict == EphemeralVerdict.INCORRECT]
    return {
        "evaluated": len(rows),
        "correct": len(correct),
        "incorrect": len(incorrect),
        "precision": round(len(correct) / len(rows), 4) if rows else None,
        "avg_confidence_correct": _mean([r.confidence for r in correct if r.confidence is not None]),
        "avg_confidence_incorrect": _mean([r.confidence for r in incorrect if r.confidence is not None]),
    }


def quality_by_source(rows: Sequence[EphemeralFeedback]) -> list[SourceQualityOut]:
    groups: dict[tuple, list[EphemeralFeedback]] = defaultdict(list)
    for row in rows:
        groups[(row.kind, row.source)].append(row)
    return [
        SourceQualityOut(kind=kind, source=source, **_quality(group))
        for (kind, source), group in sorted(groups.items(), key=lambda item: (item[0][0].value, item[0][1].value))
    ]


def quality_by_name(rows: Sequence[EphemeralFeedback]) -> list[NameQualityOut]:
    groups: dict[tuple, list[EphemeralFeedback]] = defaultdict(list)
    for row in rows:
        groups[(row.kind, row.source, row.name)].append(row)
    return [
        NameQualityOut(kind=kind, source=source, name=name, **_quality(group))
        for (kind, source, name), group in sorted(
            groups.items(), key=lambda item: (item[0][0].value, item[0][1].value, item[0][2])
        )
    ]


def confusion(rows: Sequence[EphemeralFeedback]) -> list[ConfusionOut]:
    """Labels jugés incorrects avec un `expected_name` : combien de fois « prédit » a été pris pour « attendu »."""
    counts: dict[tuple, int] = defaultdict(int)
    for row in rows:
        if row.kind == PredictionKind.LABEL and row.verdict == EphemeralVerdict.INCORRECT and row.expected_name:
            counts[(row.source, row.name, row.expected_name)] += 1
    return [
        ConfusionOut(source=source, predicted=predicted, expected=expected, count=count)
        for (source, predicted, expected), count in sorted(counts.items(), key=lambda item: (-item[1], item[0][1:]))
    ]


def agreement(predictions: Iterable[dict[str, Any]]) -> AgreementOut:
    """Accord textuel / visuel sur la classification, par page (ensembles de labels identiques)."""
    by_page: dict[tuple, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for prediction in predictions:
        if prediction["kind"] == PredictionKind.LABEL.value:
            by_page[(prediction.get("run"), prediction.get("document", 0), prediction["page_number"])][
                prediction["source"]
            ].add(prediction["name"])
    compared = [sources for sources in by_page.values() if sources.get("textual") and sources.get("visual")]
    agreeing = sum(1 for sources in compared if sources["textual"] == sources["visual"])
    return AgreementOut(
        pages_compared=len(compared),
        pages_agreeing=agreeing,
        agreement_rate=round(agreeing / len(compared), 4) if compared else None,
    )


def run_metrics(digest: EphemeralRunMetrics, feedback: Sequence[EphemeralFeedback]) -> RunMetricsOut:
    predictions = digest.predictions
    volume: list[VolumeOut] = []
    by_name: list[NameVolumeOut] = []
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for prediction in predictions:
        groups[(prediction["kind"], prediction["source"])].append(prediction)
    for (kind, source), group in sorted(groups.items()):
        confidences = [p["confidence"] for p in group if p["confidence"] is not None]
        volume.append(
            VolumeOut(
                kind=PredictionKind(kind),
                source=PredictionSource(source),
                predictions=len(group),
                pages=len({p["page_number"] for p in group}),
                avg_confidence=_mean(confidences),
                min_confidence=min(confidences) if confidences else None,
                max_confidence=max(confidences) if confidences else None,
            )
        )
        names: dict[str, list[float]] = defaultdict(list)
        counts: dict[str, int] = defaultdict(int)
        for p in group:
            counts[p["name"]] += 1
            if p["confidence"] is not None:
                names[p["name"]].append(p["confidence"])
        by_name.extend(
            NameVolumeOut(
                kind=PredictionKind(kind),
                source=PredictionSource(source),
                name=name,
                predictions=count,
                avg_confidence=_mean(names[name]),
            )
            for name, count in sorted(counts.items())
        )
    return RunMetricsOut(
        run_id=digest.run_id,
        status=digest.status,
        document_count=digest.document_count,
        page_count=digest.page_count,
        duration_seconds=digest.duration_seconds,
        steps=[StepMetricsOut(**step) for step in digest.steps],
        volume=volume,
        by_name=by_name,
        classification_agreement=agreement(predictions),
        quality=quality_by_source(feedback),
        confusion=confusion(feedback),
    )


def global_metrics(digests: Sequence[EphemeralRunMetrics], feedback: Sequence[EphemeralFeedback]) -> GlobalMetricsOut:
    # Une page s'identifie par (run, rang du document, numéro de page).
    predictions = [{**p, "run": str(digest.run_id)} for digest in digests for p in digest.predictions]
    return GlobalMetricsOut(
        runs=len(digests),
        pages=sum(digest.page_count for digest in digests),
        classification_agreement=agreement(predictions),
        quality=quality_by_source(feedback),
        by_name=quality_by_name(feedback),
        confusion=confusion(feedback),
    )


__all__ = ["QualityOut", "build_digest", "global_metrics", "run_metrics"]
