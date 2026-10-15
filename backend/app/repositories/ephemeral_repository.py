import asyncio
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors import s3_connector
from app.models.analyse_ephemere import AnalyseEphemere
from app.models.document_page import PredictionKind, PredictionSource
from app.models.dossier import Dossier
from app.models.dossier_ephemere import DossierEphemere
from app.models.ephemeral_feedback import EphemeralFeedback, EphemeralVerdict
from app.models.ephemeral_result import EphemeralResult
from app.models.ephemeral_run_metrics import EphemeralRunMetrics


class EphemeralRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_analyse_ephemere(
        self, *, analyse_id: uuid.UUID, persist: bool, created_by: str
    ) -> AnalyseEphemere:
        record = AnalyseEphemere(analyse_id=analyse_id, persist=persist, created_by=created_by)
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def get_analyse_ephemere(self, analyse_id: uuid.UUID) -> AnalyseEphemere | None:
        result = await self.db.execute(select(AnalyseEphemere).where(AnalyseEphemere.analyse_id == analyse_id))
        return result.scalar_one_or_none()

    async def create_dossier_ephemere(
        self,
        *,
        dossier_id: uuid.UUID,
        analyse_ephemere_id: uuid.UUID | None,
        persist: bool,
        ttl_hours: int,
        created_by: str,
    ) -> DossierEphemere:
        record = DossierEphemere(
            dossier_id=dossier_id,
            analyse_ephemere_id=analyse_ephemere_id,
            persist=persist,
            ttl_hours=ttl_hours,
            created_by=created_by,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def get_dossier_ephemere(self, dossier_id: uuid.UUID) -> DossierEphemere | None:
        result = await self.db.execute(select(DossierEphemere).where(DossierEphemere.dossier_id == dossier_id))
        return result.scalar_one_or_none()

    async def list_dossier_ephemeres(self, created_by: str) -> Sequence[DossierEphemere]:
        """Runs encore vivants (en cours, ou persist=True) d'un créateur."""
        result = await self.db.execute(
            select(DossierEphemere)
            .where(DossierEphemere.created_by == created_by)
            .order_by(DossierEphemere.created_at.desc())
        )
        return result.scalars().all()

    async def list_results(self, created_by: str) -> Sequence[EphemeralResult]:
        """Résultats conservés (runs persist=false terminés) d'un créateur."""
        result = await self.db.execute(
            select(EphemeralResult)
            .where(EphemeralResult.created_by == created_by)
            .order_by(EphemeralResult.created_at.desc())
        )
        return result.scalars().all()

    async def mark_dossier_terminal(self, dossier: Dossier) -> None:
        """Pose dossier_ephemere.expires_at (et la propage à
        analyse_ephemere, si le run référence une analyse elle-même
        éphémère) au premier passage du Dossier à un état terminal - voir
        docs/ephemeral-api.md, section "Principe du TTL". No-op si le
        dossier n'est pas éphémère, si persist=True, si expires_at est déjà
        posé (idempotent : jamais recalculé une fois figé) ou si le dossier
        n'a en fait pas de ended_at (pas encore terminal)."""
        if dossier.ended_at is None:
            return
        record = await self.get_dossier_ephemere(dossier.id)
        if record is None or record.persist or record.expires_at is not None:
            return
        record.expires_at = dossier.ended_at + timedelta(hours=record.ttl_hours)
        if record.analyse_ephemere_id is not None:
            analyse_ephemere = await self.db.get(AnalyseEphemere, record.analyse_ephemere_id)
            if analyse_ephemere is not None and not analyse_ephemere.persist:
                analyse_ephemere.last_run_ended_at = dossier.ended_at
                analyse_ephemere.expires_at = dossier.ended_at + timedelta(hours=record.ttl_hours)
        await self.db.commit()

    async def list_expired_dossier_ephemeres(self) -> Sequence[DossierEphemere]:
        """dossier_ephemere expirés à purger. persist=False répété ici en
        toute rigueur, même si mark_dossier_terminal ne pose jamais
        expires_at sur une ligne persist=True (defense in depth : garantit
        qu'un persist=True n'est jamais purgé même si cet invariant venait à
        être violé ailleurs)."""
        result = await self.db.execute(
            select(DossierEphemere).where(
                DossierEphemere.persist.is_(False),
                DossierEphemere.expires_at < datetime.now(UTC),
            )
        )
        return result.scalars().all()

    async def list_expired_analyse_ephemeres_without_runs(self) -> Sequence[AnalyseEphemere]:
        """analyse_ephemere expirées à purger - jamais si un dossier_ephemere
        la référence encore (même règle que le 409 de DELETE
        /api/ephemeral/analyses/{id}, cf. docs/ephemeral-api.md) : la purge
        automatique ne doit pas violer la même contrainte que la suppression
        manuelle. En pratique la purge des dossier_ephemere tourne toujours
        avant celle-ci (list_expired_dossier_ephemeres) dans la même tâche,
        donc les runs expirés sont déjà partis au moment de cet appel."""
        still_referenced = select(DossierEphemere.analyse_ephemere_id).where(
            DossierEphemere.analyse_ephemere_id.is_not(None)
        )
        result = await self.db.execute(
            select(AnalyseEphemere).where(
                AnalyseEphemere.persist.is_(False),
                AnalyseEphemere.expires_at < datetime.now(UTC),
                AnalyseEphemere.analyse_id.not_in(still_referenced),
            )
        )
        return result.scalars().all()

    # --- Résultats conservés après la fin d'un run (ephemeral_results) ---

    async def save_result(
        self,
        *,
        run_id: uuid.UUID,
        created_by: str,
        payload: dict[str, Any],
        expires_at: datetime,
        screenshot_keys: dict[str, str] | None = None,
    ) -> EphemeralResult:
        """Idempotent : réécrit l'instantané si une ligne existe déjà pour ce run. `screenshot_keys` (captures
        conservées avec le résultat) n'est réécrit que s'il est fourni."""
        record = await self.db.get(EphemeralResult, run_id)
        if record is None:
            record = EphemeralResult(
                run_id=run_id,
                created_by=created_by,
                payload=payload,
                expires_at=expires_at,
                screenshot_keys=screenshot_keys or {},
            )
            self.db.add(record)
        else:
            record.payload = payload
            record.expires_at = expires_at
            if screenshot_keys is not None:
                record.screenshot_keys = screenshot_keys
        await self.db.commit()
        return record

    async def get_result(self, run_id: uuid.UUID) -> EphemeralResult | None:
        return await self.db.get(EphemeralResult, run_id)

    async def _delete_screenshots(self, results: Sequence[EphemeralResult]) -> None:
        """Supprime de S3 les captures conservées avec ces résultats (S3Connector.delete avale les erreurs : on
        préfère un fichier orphelin à une ligne qui pointe vers des images déjà supprimées)."""
        for result in results:
            for key in result.screenshot_keys.values():
                await asyncio.to_thread(s3_connector.delete, key)

    async def delete_result(self, run_id: uuid.UUID) -> None:
        record = await self.get_result(run_id)
        if record is not None:
            await self._delete_screenshots([record])
        await self.db.execute(delete(EphemeralResult).where(EphemeralResult.run_id == run_id))
        await self.db.commit()

    async def delete_expired_results(self) -> int:
        """Supprime les résultats dont le TTL est écoulé, avec leurs captures ; renvoie leur nombre."""
        expired = (
            (await self.db.execute(select(EphemeralResult).where(EphemeralResult.expires_at < datetime.now(UTC))))
            .scalars()
            .all()
        )
        await self._delete_screenshots(expired)
        result = await self.db.execute(delete(EphemeralResult).where(EphemeralResult.expires_at < datetime.now(UTC)))
        await self.db.commit()
        return result.rowcount or 0

    # --- Condensé non sensible d'un run et verdicts des appelants (métriques) ---

    async def save_run_metrics(
        self, *, run_id: uuid.UUID, created_by: str, digest: dict[str, Any]
    ) -> EphemeralRunMetrics:
        """Idempotent : réécrit le condensé si une ligne existe déjà (un run en cours est condensé à la demande, puis
        une dernière fois à sa fin)."""
        record = await self.db.get(EphemeralRunMetrics, run_id)
        if record is None:
            record = EphemeralRunMetrics(run_id=run_id, created_by=created_by, **digest)
            self.db.add(record)
        else:
            for field, value in digest.items():
                setattr(record, field, value)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def get_run_metrics(self, run_id: uuid.UUID) -> EphemeralRunMetrics | None:
        return await self.db.get(EphemeralRunMetrics, run_id)

    async def list_run_metrics(
        self, created_by: str, *, since: datetime | None = None
    ) -> Sequence[EphemeralRunMetrics]:
        query = select(EphemeralRunMetrics).where(EphemeralRunMetrics.created_by == created_by)
        if since is not None:
            query = query.where(EphemeralRunMetrics.created_at >= since)
        return (await self.db.execute(query.order_by(EphemeralRunMetrics.created_at))).scalars().all()

    async def upsert_feedback(
        self,
        *,
        run_id: uuid.UUID,
        created_by: str,
        prediction: dict[str, Any],
        verdict: EphemeralVerdict,
        expected_name: str | None,
    ) -> EphemeralFeedback:
        """Un verdict par (run, prédiction, appelant), le dernier l'emporte. `prediction` : entrée du condensé."""
        prediction_id = uuid.UUID(prediction["id"])
        existing = (
            await self.db.execute(
                select(EphemeralFeedback).where(
                    EphemeralFeedback.run_id == run_id,
                    EphemeralFeedback.prediction_id == prediction_id,
                    EphemeralFeedback.created_by == created_by,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = EphemeralFeedback(
                run_id=run_id,
                prediction_id=prediction_id,
                created_by=created_by,
                kind=PredictionKind(prediction["kind"]),
                name=prediction["name"],
                source=PredictionSource(prediction["source"]),
                confidence=prediction["confidence"],
                page_number=prediction["page_number"],
                verdict=verdict,
                expected_name=expected_name,
            )
            self.db.add(existing)
        else:
            existing.verdict = verdict
            existing.expected_name = expected_name
        await self.db.flush()
        return existing

    async def list_feedback(
        self,
        created_by: str,
        *,
        run_id: uuid.UUID | None = None,
        kind: PredictionKind | None = None,
        source: PredictionSource | None = None,
        since: datetime | None = None,
    ) -> Sequence[EphemeralFeedback]:
        query = select(EphemeralFeedback).where(EphemeralFeedback.created_by == created_by)
        if run_id is not None:
            query = query.where(EphemeralFeedback.run_id == run_id)
        if kind is not None:
            query = query.where(EphemeralFeedback.kind == kind)
        if source is not None:
            query = query.where(EphemeralFeedback.source == source)
        if since is not None:
            query = query.where(EphemeralFeedback.created_at >= since)
        return (await self.db.execute(query.order_by(EphemeralFeedback.created_at))).scalars().all()

    async def delete_run_metrics_and_feedback(self, run_id: uuid.UUID, created_by: str) -> bool:
        """Supprime le condensé et les verdicts d'un run. Renvoie False s'il n'y avait ni l'un ni l'autre."""
        digest = await self.db.execute(
            delete(EphemeralRunMetrics).where(
                EphemeralRunMetrics.run_id == run_id, EphemeralRunMetrics.created_by == created_by
            )
        )
        feedback = await self.db.execute(
            delete(EphemeralFeedback).where(
                EphemeralFeedback.run_id == run_id, EphemeralFeedback.created_by == created_by
            )
        )
        await self.db.commit()
        return bool(digest.rowcount or feedback.rowcount)

    async def delete_metrics_older_than(self, cutoff: datetime) -> int:
        """Purge de rétention : condensés et verdicts créés avant `cutoff`. Renvoie le nombre de lignes supprimées."""
        feedback = await self.db.execute(delete(EphemeralFeedback).where(EphemeralFeedback.created_at < cutoff))
        digests = await self.db.execute(delete(EphemeralRunMetrics).where(EphemeralRunMetrics.created_at < cutoff))
        await self.db.commit()
        return (feedback.rowcount or 0) + (digests.rowcount or 0)
