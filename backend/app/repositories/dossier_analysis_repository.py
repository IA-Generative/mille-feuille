"""Accès à l'analyse de dossier (issue #112, parent #106).

Règles portées ici :
- une version n'est jamais modifiée : toute modification en ajoute une ;
- la valeur d'un instructeur devient la version *retenue* et n'écrase jamais
  la prédiction du modèle ;
- une version produite par le modèle ne remplace la version retenue que si
  aucun instructeur n'en a apporté une (sinon elle reste accessible comme
  « dernière version du modèle », cf. #119).
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dossier_analysis import (
    AnalysisElement,
    AnalysisElementKind,
    AnalysisElementVersion,
    AnalysisRevision,
    AnalysisRevisionItem,
    AnalysisUnit,
    AnalysisUnitKind,
    AnalysisUnitStatus,
    DossierAnalysis,
    ElementVersionOrigin,
)
from app.schemas.dossier_analysis import (
    AnalysisElementOut,
    DossierAnalysisOut,
    ElementVersionOut,
    InvalidElementValueError,
    RelationValue,
    validate_element_value,
)

logger = logging.getLogger(__name__)


class DossierAnalysisRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # --- Lecture ---

    async def list_analyses(self, dossier_id: uuid.UUID) -> list[DossierAnalysis]:
        result = await self.db.execute(
            select(DossierAnalysis)
            .where(DossierAnalysis.dossier_id == dossier_id)
            .order_by(DossierAnalysis.sequence.desc())
        )
        return list(result.scalars().all())

    async def get_current(self, dossier_id: uuid.UUID) -> DossierAnalysis | None:
        """Analyse la plus récente du dossier."""
        result = await self.db.execute(
            select(DossierAnalysis)
            .where(DossierAnalysis.dossier_id == dossier_id)
            .order_by(DossierAnalysis.sequence.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get(self, dossier_id: uuid.UUID, analysis_id: uuid.UUID) -> DossierAnalysis | None:
        result = await self.db.execute(
            select(DossierAnalysis).where(DossierAnalysis.id == analysis_id, DossierAnalysis.dossier_id == dossier_id)
        )
        return result.scalar_one_or_none()

    async def build_out(self, analysis: DossierAnalysis) -> DossierAnalysisOut:
        """Analyse avec ses éléments : pour chacun, la version retenue et la
        dernière version du modèle (pas tout l'historique)."""
        elements = list(
            (
                await self.db.execute(
                    select(AnalysisElement)
                    .where(AnalysisElement.analysis_id == analysis.id)
                    .order_by(AnalysisElement.created_at, AnalysisElement.id)
                )
            )
            .scalars()
            .all()
        )
        version_ids = {v for e in elements for v in (e.retained_version_id, e.latest_model_version_id) if v is not None}
        versions: dict[uuid.UUID, AnalysisElementVersion] = {}
        if version_ids:
            result = await self.db.execute(
                select(AnalysisElementVersion).where(AnalysisElementVersion.id.in_(version_ids))
            )
            versions = {v.id: v for v in result.scalars().all()}
        return DossierAnalysisOut(
            **{
                column: getattr(analysis, column)
                for column in (
                    "id",
                    "dossier_id",
                    "sequence",
                    "status",
                    "analyse_version",
                    "model",
                    "started_at",
                    "ended_at",
                    "previous_analysis_id",
                    "created_at",
                )
            },
            elements=[self._element_out(e, versions) for e in elements],
        )

    @staticmethod
    def _element_out(element: AnalysisElement, versions: dict[uuid.UUID, AnalysisElementVersion]) -> AnalysisElementOut:
        retained = versions.get(element.retained_version_id) if element.retained_version_id else None
        latest = versions.get(element.latest_model_version_id) if element.latest_model_version_id else None
        return AnalysisElementOut(
            id=element.id,
            analysis_id=element.analysis_id,
            unit_id=element.unit_id,
            kind=element.kind,
            definition_id=element.definition_id,
            definition_name=element.definition_name,
            document_id=element.document_id,
            first_page_number=element.first_page_number,
            source_prediction_id=element.source_prediction_id,
            origin_element_id=element.origin_element_id,
            needs_review=element.needs_review,
            review_reason=element.review_reason,
            retained_version=ElementVersionOut.model_validate(retained) if retained else None,
            latest_model_version=ElementVersionOut.model_validate(latest) if latest else None,
            created_at=element.created_at,
        )

    async def element_out(self, element: AnalysisElement) -> AnalysisElementOut:
        ids = [v for v in (element.retained_version_id, element.latest_model_version_id) if v is not None]
        versions: dict[uuid.UUID, AnalysisElementVersion] = {}
        if ids:
            result = await self.db.execute(select(AnalysisElementVersion).where(AnalysisElementVersion.id.in_(ids)))
            versions = {v.id: v for v in result.scalars().all()}
        return self._element_out(element, versions)

    async def list_units(self, analysis_id: uuid.UUID) -> list[AnalysisUnit]:
        result = await self.db.execute(
            select(AnalysisUnit)
            .where(AnalysisUnit.analysis_id == analysis_id)
            .order_by(AnalysisUnit.created_at, AnalysisUnit.id)
        )
        return list(result.scalars().all())

    async def get_unit(self, unit_id: uuid.UUID) -> AnalysisUnit | None:
        return await self.db.get(AnalysisUnit, unit_id)

    async def find_agent_unit(self, analysis_id: uuid.UUID, step_id: uuid.UUID) -> AnalysisUnit | None:
        result = await self.db.execute(
            select(AnalysisUnit).where(
                AnalysisUnit.analysis_id == analysis_id,
                AnalysisUnit.kind == AnalysisUnitKind.AGENT,
                AnalysisUnit.description["step_id"].astext == str(step_id),
            )
        )
        return result.scalars().first()

    async def set_unit_status(self, unit: AnalysisUnit, status: AnalysisUnitStatus) -> AnalysisUnit:
        unit.status = status
        await self.db.commit()
        return unit

    async def close_open_units(
        self, analysis_id: uuid.UUID, kind: AnalysisUnitKind, status: AnalysisUnitStatus
    ) -> None:
        """Marque les unités encore en cours d'un type (le worker s'est arrêté
        avant de les terminer)."""
        await self.db.execute(
            update(AnalysisUnit)
            .where(
                AnalysisUnit.analysis_id == analysis_id,
                AnalysisUnit.kind == kind,
                AnalysisUnit.status == AnalysisUnitStatus.EN_COURS,
            )
            .values(status=status)
        )
        await self.db.commit()

    async def get_element(self, analysis_id: uuid.UUID, element_id: uuid.UUID) -> AnalysisElement | None:
        result = await self.db.execute(
            select(AnalysisElement).where(AnalysisElement.id == element_id, AnalysisElement.analysis_id == analysis_id)
        )
        return result.scalar_one_or_none()

    async def get_element_for_update(self, analysis_id: uuid.UUID, element_id: uuid.UUID) -> AnalysisElement | None:
        """Élément avec verrou de ligne : les écritures concurrentes sur le même
        élément s'exécutent l'une après l'autre (jamais deux versions de même numéro).
        Le verrou de ligne tient jusqu'à la fin de la transaction (l'écriture)."""
        result = await self.db.execute(
            select(AnalysisElement)
            .where(AnalysisElement.id == element_id, AnalysisElement.analysis_id == analysis_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def list_versions(self, element_id: uuid.UUID) -> list[AnalysisElementVersion]:
        result = await self.db.execute(
            select(AnalysisElementVersion)
            .where(AnalysisElementVersion.element_id == element_id)
            .order_by(AnalysisElementVersion.version_number)
        )
        return list(result.scalars().all())

    # --- Création (utilisée par la génération, #113, et les propositions, #114) ---

    async def create_analysis(
        self,
        dossier_id: uuid.UUID,
        *,
        analyse_version: str | None = None,
        model: str | None = None,
        started_at: datetime | None = None,
        previous_analysis_id: uuid.UUID | None = None,
    ) -> DossierAnalysis:
        sequence = (
            await self.db.execute(
                select(func.coalesce(func.max(DossierAnalysis.sequence), 0)).where(
                    DossierAnalysis.dossier_id == dossier_id
                )
            )
        ).scalar_one() + 1
        analysis = DossierAnalysis(
            dossier_id=dossier_id,
            sequence=sequence,
            analyse_version=analyse_version,
            model=model,
            started_at=started_at,
            previous_analysis_id=previous_analysis_id,
        )
        self.db.add(analysis)
        await self.db.commit()
        return analysis

    async def create_unit(
        self,
        analysis_id: uuid.UUID,
        *,
        kind: AnalysisUnitKind,
        description: dict[str, Any] | None = None,
        input_fingerprint: str | None = None,
        status: AnalysisUnitStatus = AnalysisUnitStatus.EN_COURS,
        source_unit_id: uuid.UUID | None = None,
    ) -> AnalysisUnit:
        unit = AnalysisUnit(
            analysis_id=analysis_id,
            kind=kind,
            description=description or {},
            input_fingerprint=input_fingerprint,
            status=status,
            element_count=0,
            source_unit_id=source_unit_id,
        )
        self.db.add(unit)
        await self.db.commit()
        return unit

    async def create_element(
        self,
        analysis: DossierAnalysis,
        *,
        kind: AnalysisElementKind,
        value: dict[str, Any],
        origin: ElementVersionOrigin,
        unit: AnalysisUnit | None = None,
        definition_id: uuid.UUID | None = None,
        definition_name: str | None = None,
        document_id: uuid.UUID | None = None,
        first_page_number: int | None = None,
        source_prediction_id: uuid.UUID | None = None,
        confidence: float | None = None,
        author_id: str | None = None,
        reason: str | None = None,
        source_type: str | None = None,
        source_id: uuid.UUID | None = None,
        commit: bool = True,
    ) -> AnalysisElement:
        """Crée un élément et sa première version. Lève
        InvalidElementValueError si la valeur ne correspond pas au type."""
        clean_value = validate_element_value(kind, value)
        if kind == AnalysisElementKind.RELATION:
            await self._check_relation_endpoints(analysis.id, RelationValue.model_validate(clean_value))
        element = AnalysisElement(
            analysis_id=analysis.id,
            unit_id=unit.id if unit else None,
            kind=kind,
            definition_id=definition_id,
            definition_name=definition_name,
            document_id=document_id,
            first_page_number=first_page_number,
            source_prediction_id=source_prediction_id,
        )
        self.db.add(element)
        await self.db.flush()
        version = AnalysisElementVersion(
            element_id=element.id,
            version_number=1,
            value=clean_value,
            confidence=confidence,
            origin=origin,
            prediction_id=source_prediction_id if origin == ElementVersionOrigin.MODEL else None,
            author_id=author_id,
            reason=reason,
            source_type=source_type,
            source_id=source_id,
        )
        self.db.add(version)
        await self.db.flush()
        element.retained_version_id = version.id
        if origin == ElementVersionOrigin.MODEL:
            element.latest_model_version_id = version.id
        if unit is not None:
            # Mise à jour atomique en base (l'objet reçu peut venir d'une autre
            # session, et deux éléments peuvent être ajoutés en parallèle).
            await self.db.execute(
                update(AnalysisUnit)
                .where(AnalysisUnit.id == unit.id)
                .values(element_count=AnalysisUnit.element_count + 1)
            )
        await self._finish(commit)
        return element

    async def add_version(
        self,
        element: AnalysisElement,
        *,
        value: dict[str, Any],
        origin: ElementVersionOrigin,
        confidence: float | None = None,
        prediction_id: uuid.UUID | None = None,
        author_id: str | None = None,
        reason: str | None = None,
        source_type: str | None = None,
        source_id: uuid.UUID | None = None,
        restored_from_version_id: uuid.UUID | None = None,
        origin_version_id: uuid.UUID | None = None,
        validation_status: str | None = None,
        bounding_box_id: uuid.UUID | None = None,
        commit: bool = True,
    ) -> AnalysisElementVersion:
        """Ajoute une version à un élément et met à jour ses pointeurs.

        - une version d'instructeur devient la version retenue et efface le
          drapeau « à revoir » ;
        - une version du modèle devient la dernière version du modèle, et
          n'est retenue que si la version retenue actuelle n'est pas d'un
          instructeur."""
        clean_value = validate_element_value(element.kind, value)
        if element.kind == AnalysisElementKind.RELATION:
            await self._check_relation_endpoints(element.analysis_id, RelationValue.model_validate(clean_value))
        number = (
            await self.db.execute(
                select(func.coalesce(func.max(AnalysisElementVersion.version_number), 0)).where(
                    AnalysisElementVersion.element_id == element.id
                )
            )
        ).scalar_one() + 1
        retained = (
            await self.db.get(AnalysisElementVersion, element.retained_version_id)
            if element.retained_version_id
            else None
        )
        version = AnalysisElementVersion(
            element_id=element.id,
            version_number=number,
            value=clean_value,
            confidence=confidence,
            origin=origin,
            prediction_id=prediction_id,
            author_id=author_id,
            reason=reason,
            source_type=source_type,
            source_id=source_id,
            restored_from_version_id=restored_from_version_id,
            origin_version_id=origin_version_id,
            validation_status=validation_status,
            bounding_box_id=bounding_box_id,
        )
        self.db.add(version)
        await self.db.flush()
        if origin == ElementVersionOrigin.MODEL:
            element.latest_model_version_id = version.id
            if retained is None or retained.origin != ElementVersionOrigin.INSTRUCTOR:
                element.retained_version_id = version.id
        else:
            element.retained_version_id = version.id
            if origin == ElementVersionOrigin.INSTRUCTOR:
                element.needs_review = False
                element.review_reason = None
                await self._flag_stale_syntheses(element)
        await self._finish(commit)
        if origin == ElementVersionOrigin.INSTRUCTOR:
            await self._refresh_question_answers(element)
        return version

    async def _refresh_question_answers(self, element: AnalysisElement) -> None:
        """Une correction de l'instructeur change ce que les réponses prêtes ont lu : on les rafraîchit (celles qui
        existent, pas de nouvelle question avant la relance). N'empêche jamais la correction."""
        from app.agent.dispatch import dispatch_question_answers

        try:
            analysis = await self.db.get(DossierAnalysis, element.analysis_id)
            if analysis is not None:
                dispatch_question_answers(str(analysis.dossier_id), full=False)
        except Exception:
            logger.warning("Réponses prêtes non rafraîchies après la correction de %s", element.id, exc_info=True)

    async def restore_version(
        self,
        element: AnalysisElement,
        version: AnalysisElementVersion,
        *,
        author_id: str,
        reason: str | None,
    ) -> AnalysisElementVersion:
        """Restaure une version antérieure : ajoute une nouvelle version qui
        en reprend la valeur (rien n'est supprimé ni modifié)."""
        return await self.add_version(
            element,
            value=version.value,
            origin=ElementVersionOrigin.INSTRUCTOR,
            confidence=version.confidence,
            author_id=author_id,
            reason=reason,
            restored_from_version_id=version.id,
        )

    async def _flag_stale_syntheses(self, element: AnalysisElement) -> None:
        """Une synthèse dépend des éléments qu'elle lit : quand un instructeur en
        corrige un, les synthèses de l'analyse sont signalées « à régénérer »
        (jamais régénérées automatiquement). Elles se règlent quand l'instructeur
        les confirme ou les corrige (#119)."""
        if element.kind == AnalysisElementKind.SYNTHESIS:
            return
        await self.db.execute(
            update(AnalysisElement)
            .where(
                AnalysisElement.analysis_id == element.analysis_id,
                AnalysisElement.kind == AnalysisElementKind.SYNTHESIS,
                AnalysisElement.needs_review.is_(False),
            )
            .values(needs_review=True, review_reason="Un élément qu'elle lit a été corrigé : à régénérer.")
        )

    async def _finish(self, commit: bool) -> None:
        """Valide la transaction, ou seulement l'envoie en base quand l'appelant
        regroupe plusieurs écritures dans une même transaction (propositions)."""
        if commit:
            await self.db.commit()
        else:
            await self.db.flush()

    async def _check_relation_endpoints(self, analysis_id: uuid.UUID, value: RelationValue) -> None:
        ids = {value.source_element_id, value.target_element_id}
        found = (
            await self.db.execute(
                select(func.count())
                .select_from(AnalysisElement)
                .where(AnalysisElement.analysis_id == analysis_id, AnalysisElement.id.in_(ids))
            )
        ).scalar_one()
        if found != len(ids):
            raise InvalidElementValueError("Une relation doit relier des éléments existants de la même analyse")

    # --- Révisions ---

    async def list_revisions(self, analysis_id: uuid.UUID) -> list[AnalysisRevision]:
        result = await self.db.execute(
            select(AnalysisRevision)
            .where(AnalysisRevision.analysis_id == analysis_id)
            .order_by(AnalysisRevision.number.desc())
        )
        return list(result.scalars().all())

    async def get_revision(self, analysis_id: uuid.UUID, revision_id: uuid.UUID) -> AnalysisRevision | None:
        result = await self.db.execute(
            select(AnalysisRevision).where(
                AnalysisRevision.id == revision_id, AnalysisRevision.analysis_id == analysis_id
            )
        )
        return result.scalar_one_or_none()

    async def list_revision_items(self, revision_id: uuid.UUID) -> list[AnalysisRevisionItem]:
        result = await self.db.execute(
            select(AnalysisRevisionItem).where(AnalysisRevisionItem.revision_id == revision_id)
        )
        return list(result.scalars().all())

    async def create_revision(
        self, analysis: DossierAnalysis, *, author_id: str | None, label: str | None
    ) -> tuple[AnalysisRevision, list[AnalysisRevisionItem]]:
        """Instantané : la version retenue de chaque élément (les éléments
        sans version retenue sont ignorés)."""
        number = (
            await self.db.execute(
                select(func.coalesce(func.max(AnalysisRevision.number), 0)).where(
                    AnalysisRevision.analysis_id == analysis.id
                )
            )
        ).scalar_one() + 1
        revision = AnalysisRevision(analysis_id=analysis.id, number=number, label=label, author_id=author_id)
        self.db.add(revision)
        await self.db.flush()
        rows = (
            await self.db.execute(
                select(AnalysisElement.id, AnalysisElement.retained_version_id).where(
                    AnalysisElement.analysis_id == analysis.id, AnalysisElement.retained_version_id.is_not(None)
                )
            )
        ).all()
        items = [AnalysisRevisionItem(revision_id=revision.id, element_id=eid, version_id=vid) for eid, vid in rows]
        self.db.add_all(items)
        await self.db.commit()
        return revision, items
