import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext
from app.models.dossier import Dossier
from app.models.work_slot import WorkSlot
from app.schemas.work_slot import SlotIn
from app.services.dossier_access import visible_clause


class WorkSlotRepository:
    """Créneaux de traitement (issue #174). Chaque méthode est **bornée à un propriétaire** : il n'existe aucune
    lecture ni écriture qui ne passe par `user_id`, pour qu'un créneau ne soit jamais visible d'un autre."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for(self, user: RequestContext) -> Sequence[WorkSlot]:
        """Mes créneaux sur les dossiers que je vois encore (issue #177)."""
        result = await self.db.execute(
            select(WorkSlot)
            .join(Dossier, Dossier.id == WorkSlot.dossier_id)
            .where(WorkSlot.user_id == user.user_id, visible_clause(user))
            .order_by(WorkSlot.start_at, WorkSlot.id)
        )
        return result.scalars().all()

    async def map_for(self, user_id: str, dossier_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, WorkSlot]:
        if not dossier_ids:
            return {}
        result = await self.db.execute(
            select(WorkSlot).where(WorkSlot.user_id == user_id, WorkSlot.dossier_id.in_(dossier_ids))
        )
        return {slot.dossier_id: slot for slot in result.scalars().all()}

    async def upsert(self, user_id: str, dossier_id: uuid.UUID, data: SlotIn) -> WorkSlot:
        """Pose ou remplace le créneau de la personne pour ce dossier (un seul par couple)."""
        values = {
            "user_id": user_id,
            "dossier_id": dossier_id,
            "start_at": data.start,
            "end_at": data.end,
            "recurrence": data.recurrence.model_dump(mode="json") if data.recurrence else None,
            "reminders": data.reminders,
        }
        statement = insert(WorkSlot).values(id=uuid.uuid4(), **values)
        statement = statement.on_conflict_do_update(
            constraint="uq_work_slots_user_dossier",
            # `updated_at` est bumpé à la main : `onupdate` du modèle ne joue pas pour un INSERT … ON CONFLICT. Les
            # rappels (#219) ne partent que pour des instants postérieurs à cette date.
            set_={**{k: statement.excluded[k] for k in values if k != "user_id"}, "updated_at": func.now()},
        ).returning(WorkSlot)
        slot = (await self.db.execute(statement, execution_options={"populate_existing": True})).scalar_one()
        await self.db.commit()
        return slot

    async def delete(self, user_id: str, dossier_id: uuid.UUID) -> None:
        await self.db.execute(delete(WorkSlot).where(WorkSlot.user_id == user_id, WorkSlot.dossier_id == dossier_id))
        await self.db.commit()
