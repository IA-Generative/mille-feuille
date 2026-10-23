"""État de l'index de recherche d'un dossier et reconstruction blue/green.

Le backend ne touche jamais Qdrant : il tient l'état (quels réglages ont produit l'index, où en est une
reconstruction) et dépose les tâches que le worker exécute. Une reconstruction suit le modèle de Muffin :
`building` (le nouvel index se construit, l'actif répond encore) → `swapped` (l'alias a basculé, l'ancien est gardé) →
`finalized` (validée, l'ancien est supprimé) ou `rolled_back` (retour à l'ancien) ; `failed` si la construction échoue.
Un dossier a au plus une reconstruction dans les états `building` et `swapped`."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import celery_client
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
        if report.status is not None and report.status != rebuild.status:
            rebuild.status = report.status
            now = datetime.now(UTC)
            if report.status == IndexRebuildStatus.SWAPPED:
                rebuild.swapped_at = now
            elif report.status in (IndexRebuildStatus.FAILED, IndexRebuildStatus.ROLLED_BACK):
                rebuild.finished_at = now
        await self.db.commit()
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
        rebuild.status = IndexRebuildStatus.ROLLED_BACK
        rebuild.finished_at = datetime.now(UTC)
        await self.db.commit()
        celery_client.dispatch_rollback_rebuild(str(rebuild.id))
        return rebuild
