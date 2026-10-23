"""État de l'index de recherche d'un dossier et reconstruction blue/green.

Le backend ne touche jamais Qdrant : il tient l'état (quels réglages ont produit l'index, où en est une
reconstruction) et dépose les tâches que le worker exécute. Une reconstruction suit le modèle de Muffin :
`building` (le nouvel index se construit, l'actif répond encore) → `swapped` (l'alias a basculé, l'ancien est gardé) →
`finalized` (validée, l'ancien est supprimé) ou `rolled_back` (retour à l'ancien) ; `failed` si la construction échoue.
Un dossier a au plus une reconstruction dans les états `building` et `swapped`."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import celery_client
from app.config import SearchSettings as PlatformSearchSettings
from app.models.analyse import Analyse
from app.models.dossier import Dossier
from app.models.search_index import (
    ACTIVE_REBUILD_STATUSES,
    DossierSearchIndex,
    IndexRebuild,
    IndexRebuildStatus,
    SearchIndexStatus,
)
from app.schemas.search_index import (
    AnalyseIndexOverview,
    IndexRebuildOut,
    IndexStateOut,
    RebuildReport,
    SearchConfigOut,
    SearchIndexReport,
)
from app.services.search import settings as search_settings


class RebuildInProgressError(Exception):
    """Le dossier a déjà une reconstruction en cours, ou basculée et pas encore validée."""


class NothingToRebuildError(Exception):
    """L'index est déjà à jour avec les réglages de l'analyse."""


class RebuildNotFoundError(Exception):
    pass


class RebuildStateError(Exception):
    """La reconstruction n'est pas dans un état qui permet cette action."""


class SettingsUnresolvedError(Exception):
    """Les réglages de l'analyse ne se résolvent pas (par exemple : aucun modèle d'embeddings)."""


def _resolve(analyse: Analyse | None) -> tuple[search_settings.EffectiveSearchSettings | None, str | None]:
    if analyse is None:
        return None, "Le dossier n'a pas d'analyse"
    try:
        return search_settings.resolve(analyse.search_settings), None
    except ValueError as error:
        return None, str(error)


def _resolve_stored(stored: dict) -> tuple[search_settings.EffectiveSearchSettings | None, str | None]:
    try:
        return search_settings.resolve(stored), None
    except ValueError as error:
        return None, str(error)


class SearchIndexService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -- lecture ---------------------------------------------------------------------------------------------------

    async def _dossier_analyse(self, dossier_id: uuid.UUID) -> Analyse | None:
        dossier = await self.db.get(Dossier, dossier_id)
        if dossier is None or dossier.analyse_id is None:
            return None
        return await self.db.get(Analyse, dossier.analyse_id)

    async def index(self, dossier_id: uuid.UUID) -> DossierSearchIndex | None:
        return await self.db.get(DossierSearchIndex, dossier_id)

    async def active_rebuild(self, dossier_id: uuid.UUID) -> IndexRebuild | None:
        result = await self.db.execute(
            select(IndexRebuild).where(
                IndexRebuild.dossier_id == dossier_id, IndexRebuild.status.in_(ACTIVE_REBUILD_STATUSES)
            )
        )
        return result.scalar_one_or_none()

    async def latest_rebuild(self, dossier_id: uuid.UUID) -> IndexRebuild | None:
        """La reconstruction en cours, sinon la dernière terminée : l'écran montre l'une ou l'autre."""
        active = await self.active_rebuild(dossier_id)
        if active is not None:
            return active
        result = await self.db.execute(
            select(IndexRebuild)
            .where(IndexRebuild.dossier_id == dossier_id)
            .order_by(IndexRebuild.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def state(self, dossier_id: uuid.UUID) -> IndexStateOut:
        analyse = await self._dossier_analyse(dossier_id)
        effective, problem = _resolve(analyse)
        expected = effective.fingerprint if effective else None
        index = await self.index(dossier_id)
        rebuild = await self.latest_rebuild(dossier_id)
        out = IndexRebuildOut.model_validate(rebuild) if rebuild else None
        if index is None:
            return IndexStateOut(freshness="none", expected_fingerprint=expected, problem=problem, rebuild=out)
        freshness = "current" if expected is not None and index.fingerprint == expected else "obsolete"
        return IndexStateOut(
            freshness=freshness,
            status=index.status,
            fingerprint=index.fingerprint,
            expected_fingerprint=expected,
            problem=problem,
            chunk_count=index.chunk_count,
            error=index.error,
            indexed_at=index.indexed_at,
            rebuild=out,
        )

    async def config(self, dossier_id: uuid.UUID) -> SearchConfigOut:
        """Ce que le worker doit savoir : les réglages à appliquer à un premier index, l'index actif et la
        reconstruction en cours."""
        analyse = await self._dossier_analyse(dossier_id)
        effective, problem = _resolve(analyse)
        index = await self.index(dossier_id)
        rebuild = await self.active_rebuild(dossier_id)
        return SearchConfigOut(
            dossier_id=dossier_id,
            effective=effective.model_dump() if effective else None,
            fingerprint=effective.fingerprint if effective else None,
            problem=problem,
            index_fingerprint=index.fingerprint if index else None,
            index_settings=index.settings if index else None,
            index_status=index.status if index else None,
            rebuild=IndexRebuildOut.model_validate(rebuild) if rebuild else None,
            rebuild_target_settings=rebuild.target_settings if rebuild else None,
            rebuild_previous_settings=rebuild.previous_settings if rebuild else None,
        )

    # -- compte rendu du worker ------------------------------------------------------------------------------------

    async def report_index(self, dossier_id: uuid.UUID, report: SearchIndexReport) -> DossierSearchIndex:
        index = await self.index(dossier_id)
        if index is None:
            if report.fingerprint is None or report.settings is None:
                raise ValueError("Premier compte rendu : l'empreinte et les réglages sont obligatoires")
            index = DossierSearchIndex(
                dossier_id=dossier_id, fingerprint=report.fingerprint, settings=report.settings, chunk_count=0
            )
            self.db.add(index)
        elif report.replace_settings and report.fingerprint is not None and report.settings is not None:
            index.fingerprint, index.settings = report.fingerprint, report.settings
        index.status = report.status
        index.chunk_count = report.chunk_count
        index.error = report.error
        if report.status == SearchIndexStatus.READY:
            index.indexed_at = datetime.now(UTC)
        await self.db.commit()
        return index

    async def report_rebuild(self, rebuild_id: uuid.UUID, report: RebuildReport) -> IndexRebuild:
        rebuild = await self.db.get(IndexRebuild, rebuild_id)
        if rebuild is None:
            raise RebuildNotFoundError
        if report.total_pages is not None:
            rebuild.total_pages = report.total_pages
        if report.done_pages is not None:
            rebuild.done_pages = report.done_pages
        if report.error is not None:
            rebuild.error = report.error
        was_building = rebuild.status == IndexRebuildStatus.BUILDING
        if report.status is not None and report.status != rebuild.status:
            rebuild.status = report.status
            now = datetime.now(UTC)
            if report.status == IndexRebuildStatus.SWAPPED:
                rebuild.swapped_at = now
            elif report.status in (IndexRebuildStatus.FAILED, IndexRebuildStatus.ROLLED_BACK):
                rebuild.finished_at = now
        await self.db.commit()
        if was_building and rebuild.status != IndexRebuildStatus.BUILDING:
            await self._promote_queued(rebuild.dossier_id)
        return rebuild

    # -- reconstruction ---------------------------------------------------------------------------------------------

    async def start_rebuild(self, dossier_id: uuid.UUID, user_id: str) -> IndexRebuild:
        """Démarre la reconstruction de l'index avec les réglages actuels de l'analyse. Sans index, c'est une première
        indexation ; avec un index à jour et en bon état, il n'y a rien à faire."""
        effective, problem = _resolve(await self._dossier_analyse(dossier_id))
        if effective is None:
            raise SettingsUnresolvedError(problem)
        if await self.active_rebuild(dossier_id) is not None:
            raise RebuildInProgressError
        index = await self.index(dossier_id)
        if index and index.fingerprint == effective.fingerprint and index.status == SearchIndexStatus.READY:
            raise NothingToRebuildError
        rebuild = IndexRebuild(
            dossier_id=dossier_id,
            status=IndexRebuildStatus.BUILDING,
            target_fingerprint=effective.fingerprint,
            target_settings=effective.model_dump(),
            previous_fingerprint=index.fingerprint if index else None,
            previous_settings=index.settings if index else None,
            total_pages=0,
            done_pages=0,
            requested_by=user_id,
        )
        self.db.add(rebuild)
        try:
            await self.db.commit()
        except IntegrityError as error:
            await self.db.rollback()
            raise RebuildInProgressError from error
        celery_client.dispatch_rebuild_index(str(rebuild.id))
        return rebuild

    async def _owned(self, dossier_id: uuid.UUID, rebuild_id: uuid.UUID) -> IndexRebuild:
        rebuild = await self.db.get(IndexRebuild, rebuild_id)
        if rebuild is None or rebuild.dossier_id != dossier_id:
            raise RebuildNotFoundError
        return rebuild

    async def validate(self, dossier_id: uuid.UUID, rebuild_id: uuid.UUID) -> IndexRebuild:
        """Valide la bascule : l'ancien index est supprimé et ne pourra plus être rétabli."""
        rebuild = await self._owned(dossier_id, rebuild_id)
        if rebuild.status != IndexRebuildStatus.SWAPPED:
            raise RebuildStateError("Seule une reconstruction basculée peut être validée")
        rebuild.status = IndexRebuildStatus.FINALIZED
        rebuild.finished_at = datetime.now(UTC)
        await self.db.commit()
        celery_client.dispatch_finalize_rebuild(str(rebuild.id))
        return rebuild

    async def rollback(self, dossier_id: uuid.UUID, rebuild_id: uuid.UUID) -> IndexRebuild:
        """Annule une reconstruction : en cours, elle s'arrête ; basculée, l'alias revient sur l'ancien index. Dans les
        deux cas le nouvel index est supprimé."""
        rebuild = await self._owned(dossier_id, rebuild_id)
        if rebuild.status not in ACTIVE_REBUILD_STATUSES:
            raise RebuildStateError("Cette reconstruction est terminée")
        if rebuild.status == IndexRebuildStatus.SWAPPED:
            index = await self.index(dossier_id)
            if index is not None and rebuild.previous_fingerprint and rebuild.previous_settings:
                index.fingerprint, index.settings = rebuild.previous_fingerprint, rebuild.previous_settings
        was_building = rebuild.status == IndexRebuildStatus.BUILDING
        rebuild.status = IndexRebuildStatus.ROLLED_BACK
        rebuild.finished_at = datetime.now(UTC)
        await self.db.commit()
        celery_client.dispatch_rollback_rebuild(str(rebuild.id))
        if was_building:
            await self._promote_queued(dossier_id)
        return rebuild

    # -- reconstruction en lot d'une analyse --------------------------------------------------------------------------

    async def _analyse_of(self, dossier_id: uuid.UUID) -> uuid.UUID | None:
        dossier = await self.db.get(Dossier, dossier_id)
        return dossier.analyse_id if dossier else None

    async def _building_count(self, analyse_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(IndexRebuild)
            .join(Dossier, Dossier.id == IndexRebuild.dossier_id)
            .where(Dossier.analyse_id == analyse_id, IndexRebuild.status == IndexRebuildStatus.BUILDING)
        )
        return result.scalar_one()

    async def _promote_queued(self, dossier_id: uuid.UUID) -> None:
        """Une place s'est libérée dans l'analyse du dossier : les reconstructions en attente démarrent, de la plus
        ancienne à la plus récente, tant qu'il reste de la place."""
        analyse_id = await self._analyse_of(dossier_id)
        if analyse_id is None:
            return
        room = PlatformSearchSettings().SEARCH_MAX_PARALLEL_REBUILDS - await self._building_count(analyse_id)
        if room <= 0:
            return
        result = await self.db.execute(
            select(IndexRebuild)
            .join(Dossier, Dossier.id == IndexRebuild.dossier_id)
            .where(Dossier.analyse_id == analyse_id, IndexRebuild.status == IndexRebuildStatus.QUEUED)
            .order_by(IndexRebuild.created_at)
            .limit(room)
        )
        started = list(result.scalars())
        for rebuild in started:
            rebuild.status = IndexRebuildStatus.BUILDING
        await self.db.commit()
        for rebuild in started:
            celery_client.dispatch_rebuild_index(str(rebuild.id))

    async def _indexed_dossiers(self, analyse_id: uuid.UUID) -> list[tuple[uuid.UUID, DossierSearchIndex]]:
        result = await self.db.execute(
            select(Dossier.id, DossierSearchIndex)
            .join(DossierSearchIndex, DossierSearchIndex.dossier_id == Dossier.id)
            .where(Dossier.analyse_id == analyse_id)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def overview(self, analyse: Analyse, settings: dict | None = None) -> AnalyseIndexOverview:
        """Où en sont les index des dossiers de l'analyse, pour les réglages donnés (par défaut ceux de l'analyse) :
        c'est aussi ce qui dit combien de dossiers un changement de réglages rendrait obsolètes."""
        effective, _ = _resolve(analyse) if settings is None else _resolve_stored(settings)
        expected = effective.fingerprint if effective else None
        indexed = await self._indexed_dossiers(analyse.id)
        active = {
            row.dossier_id: row.status
            for row in (
                await self.db.execute(
                    select(IndexRebuild.dossier_id, IndexRebuild.status)
                    .join(Dossier, Dossier.id == IndexRebuild.dossier_id)
                    .where(Dossier.analyse_id == analyse.id, IndexRebuild.status.in_(ACTIVE_REBUILD_STATUSES))
                )
            ).all()
        }
        total = (
            await self.db.execute(select(func.count()).select_from(Dossier).where(Dossier.analyse_id == analyse.id))
        ).scalar_one()
        obsolete = sum(1 for _, index in indexed if expected is None or index.fingerprint != expected)
        return AnalyseIndexOverview(
            dossiers=total,
            indexed=len(indexed),
            current=len(indexed) - obsolete,
            obsolete=obsolete,
            errors=sum(1 for _, index in indexed if index.status == SearchIndexStatus.ERROR),
            rebuilding=sum(1 for status in active.values() if status == IndexRebuildStatus.BUILDING),
            queued=sum(1 for status in active.values() if status == IndexRebuildStatus.QUEUED),
            to_validate=sum(1 for status in active.values() if status == IndexRebuildStatus.SWAPPED),
        )

    async def rebuild_analyse(self, analyse: Analyse, user_id: str) -> list[IndexRebuild]:
        """Reconstruit l'index de chaque dossier indexé de l'analyse dont l'empreinte n'est plus celle des réglages (ou
        dont l'index est en erreur). Le nombre de reconstructions simultanées est plafonné : les autres attendent leur
        tour et démarrent à mesure que des places se libèrent."""
        effective, problem = _resolve(analyse)
        if effective is None:
            raise SettingsUnresolvedError(problem)
        busy = {
            row[0]
            for row in (
                await self.db.execute(
                    select(IndexRebuild.dossier_id)
                    .join(Dossier, Dossier.id == IndexRebuild.dossier_id)
                    .where(Dossier.analyse_id == analyse.id, IndexRebuild.status.in_(ACTIVE_REBUILD_STATUSES))
                )
            ).all()
        }
        room = PlatformSearchSettings().SEARCH_MAX_PARALLEL_REBUILDS - await self._building_count(analyse.id)
        created: list[IndexRebuild] = []
        for dossier_id, index in await self._indexed_dossiers(analyse.id):
            if dossier_id in busy:
                continue
            if index.fingerprint == effective.fingerprint and index.status == SearchIndexStatus.READY:
                continue
            status = IndexRebuildStatus.BUILDING if room > 0 else IndexRebuildStatus.QUEUED
            room -= 1
            rebuild = IndexRebuild(
                dossier_id=dossier_id,
                status=status,
                target_fingerprint=effective.fingerprint,
                target_settings=effective.model_dump(),
                previous_fingerprint=index.fingerprint,
                previous_settings=index.settings,
                total_pages=0,
                done_pages=0,
                requested_by=user_id,
            )
            self.db.add(rebuild)
            created.append(rebuild)
        await self.db.commit()
        for rebuild in created:
            if rebuild.status == IndexRebuildStatus.BUILDING:
                celery_client.dispatch_rebuild_index(str(rebuild.id))
        return created
