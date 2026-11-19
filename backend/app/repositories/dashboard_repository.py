from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Date, Float, and_, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext
from app.models.analyse import Analyse, StatusDefinition
from app.models.dossier import Dossier
from app.models.dossier_event import DossierEvent
from app.repositories.work_slot_repository import WorkSlotRepository
from app.schemas.dashboard import (
    DashboardActivityOut,
    DashboardOtherOut,
    DashboardStatsOut,
    DashboardStatusCountOut,
    DashboardUnassignedOut,
    DashboardUrgencyOut,
)
from app.schemas.work_slot import SlotOut
from app.services.dashboard_stats import ACTIVITY_KINDS, activity_message, bucket_by_week, week_windows
from app.services.dossier_access import visible_clause
from app.services.due_date import PARIS, due_info, today_in_paris

URGENCY_LIMIT = 200
UNASSIGNED_LIMIT = 50
ACTIVITY_LIMIT = 20
ACTIVITY_DAYS = 7


class DashboardRepository:
    """Lectures du tableau de bord personnel (issue #174) : ce qui est affecté à la personne, rien de plus."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _mine(user: RequestContext) -> list:
        # Les dossiers « à ranger » (sans analyse) n'ont ni statut ni seuils : ils n'entrent pas ici. Un dossier qu'on
        # ne voit plus (retrait d'accès, #177) n'est plus dans ses indicateurs, ses urgences ni son activité.
        return [
            Dossier.assignee_id == user.user_id,
            Dossier.analyse_id.is_not(None),
            visible_clause(user.is_admin, user.groups),
        ]

    async def stats(self, user: RequestContext, today: date) -> DashboardStatsOut:
        mine = self._mine(user)
        windows = week_windows(today, 4)
        closed_rows = await self.db.execute(
            select(Dossier.closed_at).where(*mine, Dossier.closed_at >= windows[0][0], Dossier.closed_at.is_not(None))
        )
        weekly = bucket_by_week([row[0] for row in closed_rows.all()], windows)

        closed_day = cast(func.timezone(PARIS.key, Dossier.closed_at), Date)
        aggregate = await self.db.execute(
            select(
                func.count(),
                func.count(Dossier.closed_at),
                func.avg(cast(func.extract("epoch", Dossier.closed_at - Dossier.created_at), Float) / 86400.0),
                func.count(case((Dossier.due_at.is_not(None), 1), else_=None)).filter(Dossier.closed_at.is_not(None)),
                func.count(case((and_(Dossier.due_at.is_not(None), closed_day <= Dossier.due_at), 1), else_=None)),
            ).where(*mine)
        )
        total, closed, average, with_due, on_time = aggregate.one()
        return DashboardStatsOut(
            total_dossiers=total,
            closed_dossiers=closed,
            completed_this_week=weekly[-1],
            completed_prev_week=weekly[-2],
            weekly_closed=weekly,
            avg_processing_days=round(float(average), 1) if average is not None else 0.0,
            on_time_rate=round(on_time / with_due, 2) if with_due else 0.0,
        )

    async def agenda(self, user: RequestContext) -> tuple[list[DashboardUrgencyOut], list[DashboardOtherOut]]:
        """Mes dossiers ouverts, pour l'agenda : d'un côté les urgences (échéance proche ou dépassée selon les seuils
        de leur analyse, #172), de l'autre les autres (échéance lointaine ou absente), qu'on veut aussi pouvoir
        planifier."""
        result = await self.db.execute(
            select(Dossier, Analyse.name, Analyse.due_thresholds, StatusDefinition.name)
            .join(Analyse, Analyse.id == Dossier.analyse_id)
            .outerjoin(StatusDefinition, StatusDefinition.id == Dossier.workflow_status_id)
            .where(*self._mine(user), Dossier.closed_at.is_(None))
            .order_by(Dossier.due_at.asc().nulls_last(), Dossier.ref_number.asc())
        )
        today = today_in_paris()
        rows = result.all()
        slots = await WorkSlotRepository(self.db).map_for(user.user_id, [row[0].id for row in rows])
        urgencies: list[DashboardUrgencyOut] = []
        others: list[DashboardOtherOut] = []
        for dossier, analyse_name, thresholds, status_name in rows:
            slot = SlotOut.model_validate(slots[dossier.id]) if dossier.id in slots else None
            info = due_info(dossier.due_at, thresholds, today)
            if info is not None and info.level in ("soon", "overdue"):
                if len(urgencies) < URGENCY_LIMIT:
                    urgencies.append(
                        DashboardUrgencyOut(
                            dossier_id=dossier.id,
                            dossier_name=dossier.name,
                            analyse_id=dossier.analyse_id,
                            analyse_name=analyse_name,
                            status_label=status_name,
                            due_at=dossier.due_at,
                            level=info.level,
                            days_left=info.days_left,
                            color=info.color,
                            slot=slot,
                        )
                    )
            elif len(others) < URGENCY_LIMIT:
                others.append(
                    DashboardOtherOut(
                        dossier_id=dossier.id,
                        dossier_name=dossier.name,
                        analyse_id=dossier.analyse_id,
                        analyse_name=analyse_name,
                        status_label=status_name,
                        due_at=dossier.due_at,
                        slot=slot,
                    )
                )
        return urgencies, others

    async def status_counts(self, user: RequestContext) -> list[DashboardStatusCountOut]:
        """Mes dossiers ouverts par statut, dans l'ordre des statuts (les statuts finaux n'y figurent pas)."""
        result = await self.db.execute(
            select(StatusDefinition.id, StatusDefinition.name, Analyse.name, func.count())
            .join(Dossier, Dossier.workflow_status_id == StatusDefinition.id)
            .join(Analyse, Analyse.id == StatusDefinition.analyse_id)
            .where(*self._mine(user), StatusDefinition.is_final.is_(False))
            .group_by(StatusDefinition.id, StatusDefinition.name, StatusDefinition.position, Analyse.name)
            .order_by(Analyse.name, StatusDefinition.position)
        )
        return [
            DashboardStatusCountOut(status_id=i, label=name, analyse_name=analyse, count=count)
            for i, name, analyse, count in result.all()
        ]

    async def unassigned(self, user: RequestContext) -> list[DashboardUnassignedOut]:
        """Dossiers ouverts sans responsable, les plus anciens d'abord (ce sont ceux qui attendent le plus)."""
        result = await self.db.execute(
            select(Dossier.id, Dossier.name, Analyse.name, Dossier.created_at)
            .join(Analyse, Analyse.id == Dossier.analyse_id)
            .where(
                Dossier.assignee_id.is_(None),
                Dossier.closed_at.is_(None),
                visible_clause(user.is_admin, user.groups),
            )
            .order_by(Dossier.created_at.asc(), Dossier.ref_number.asc())
            .limit(UNASSIGNED_LIMIT)
        )
        return [
            DashboardUnassignedOut(dossier_id=i, dossier_name=name, analyse_name=analyse, created_at=created)
            for i, name, analyse, created in result.all()
        ]

    async def activity(self, user: RequestContext) -> list[DashboardActivityOut]:
        """Ce qui s'est passé sur mes dossiers ces derniers jours, **par d'autres** (on ne se notifie pas soi-même)."""
        since = datetime.now(UTC) - timedelta(days=ACTIVITY_DAYS)
        result = await self.db.execute(
            select(DossierEvent, Dossier.name)
            .join(Dossier, Dossier.id == DossierEvent.dossier_id)
            .where(
                *self._mine(user),
                DossierEvent.type.in_(list(ACTIVITY_KINDS)),
                DossierEvent.created_at >= since,
                DossierEvent.actor_id.is_distinct_from(user.user_id),
            )
            .order_by(DossierEvent.created_at.desc(), DossierEvent.seq.desc())
            .limit(ACTIVITY_LIMIT)
        )
        return [
            DashboardActivityOut(
                id=event.id,
                kind=ACTIVITY_KINDS[event.type],
                dossier_id=event.dossier_id,
                dossier_name=name,
                message=activity_message(event.type, event.payload, event.actor_name),
                at=event.created_at,
            )
            for event, name in result.all()
        ]
