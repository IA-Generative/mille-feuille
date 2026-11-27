"""Verrou court par élément et présence (issue #118, parent #106).

**Verrou** : porté par l'élément (``locked_by``, ``locked_until``). L'acquisition est
**atomique** (un seul UPDATE conditionnel) : deux instructeurs qui le demandent en
même temps, un seul l'obtient. Il expire seul (``ELEMENT_LOCK_TTL_SECONDS``) : un
instructeur qui part sans enregistrer ne bloque personne durablement. Il n'est pas
obligatoire pour écrire, mais **une écriture est refusée tant qu'un autre
instructeur détient un verrou valide** sur l'élément.

**Présence** : éphémère, mise à jour par battement de cœur, ignorée passé
``PRESENCE_TTL_SECONDS``."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CollaborationSettings
from app.models.dossier_analysis import AnalysisElement, AnalysisPresence
from app.schemas.analysis_collaboration import LiveSnapshot, LockOut, PresenceOut
from app.utils.sorting import sort_key

settings = CollaborationSettings()


class ElementLockedError(Exception):
    """L'élément est verrouillé par un autre instructeur."""

    def __init__(self, holder_name: str | None, holder_id: str, until: datetime) -> None:
        self.holder_name = holder_name or holder_id
        self.holder_id = holder_id
        self.until = until
        super().__init__(self.message)

    @property
    def message(self) -> str:
        return (
            f"Cet élément est en cours de modification par {self.holder_name} "
            f"(verrou jusqu'à {self.until.astimezone(UTC).strftime('%H:%M')} UTC) : réessayez dans un instant."
        )


def display_name(user) -> str:
    """Nom affiché d'un utilisateur (prénom et nom, sinon e-mail, sinon identifiant)."""
    full = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
    return full or getattr(user, "email", "") or user.user_id


def lock_is_valid(element: AnalysisElement, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return element.locked_by is not None and element.locked_until is not None and element.locked_until > now


def ensure_not_locked_by_other(element: AnalysisElement, user_id: str) -> None:
    """Refuse l'écriture si un autre instructeur détient un verrou valide."""
    if lock_is_valid(element) and element.locked_by != user_id:
        raise ElementLockedError(element.locked_by_name, element.locked_by or "", element.locked_until)


async def release_if_holder(db: AsyncSession, element: AnalysisElement, user_id: str) -> None:
    """Après une écriture réussie, le détenteur du verrou le libère (l'édition est finie)."""
    if element.locked_by == user_id:
        element.locked_by = None
        element.locked_by_name = None
        element.locked_until = None


class AnalysisCollaborationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # --- Verrou ---

    async def acquire_lock(
        self, analysis_id: uuid.UUID, element_id: uuid.UUID, *, user_id: str, name: str
    ) -> AnalysisElement | None:
        """Prend ou renouvelle le verrou. Atomique : renvoie None si un autre
        instructeur en détient un valide."""
        result = await self.db.execute(
            update(AnalysisElement)
            .where(
                AnalysisElement.id == element_id,
                AnalysisElement.analysis_id == analysis_id,
                or_(
                    AnalysisElement.locked_by.is_(None),
                    AnalysisElement.locked_until.is_(None),
                    AnalysisElement.locked_until <= func.now(),
                    AnalysisElement.locked_by == user_id,
                ),
            )
            .values(
                locked_by=user_id,
                locked_by_name=name,
                locked_until=func.now() + timedelta(seconds=settings.ELEMENT_LOCK_TTL_SECONDS),
            )
            .returning(AnalysisElement.id)
            .execution_options(synchronize_session=False)
        )
        acquired = result.first() is not None
        await self.db.commit()
        if not acquired:
            return None
        return await self.get_element(analysis_id, element_id)

    async def release_lock(self, analysis_id: uuid.UUID, element_id: uuid.UUID, *, user_id: str) -> bool:
        """Libère le verrou de l'utilisateur. False si un autre en détient un valide."""
        element = await self.get_element(analysis_id, element_id)
        if element is None or not lock_is_valid(element):
            return True
        if element.locked_by != user_id:
            return False
        await self.db.execute(
            update(AnalysisElement)
            .where(AnalysisElement.id == element_id, AnalysisElement.locked_by == user_id)
            .values(locked_by=None, locked_by_name=None, locked_until=None)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()
        return True

    async def get_element(self, analysis_id: uuid.UUID, element_id: uuid.UUID) -> AnalysisElement | None:
        result = await self.db.execute(
            select(AnalysisElement)
            .where(AnalysisElement.id == element_id, AnalysisElement.analysis_id == analysis_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def list_locks(self, analysis_id: uuid.UUID, *, current_user_id: str) -> list[LockOut]:
        result = await self.db.execute(
            select(AnalysisElement)
            .where(
                AnalysisElement.analysis_id == analysis_id,
                AnalysisElement.locked_by.is_not(None),
                AnalysisElement.locked_until > func.now(),
            )
            .order_by(AnalysisElement.id)
            .execution_options(populate_existing=True)
        )
        return [lock_out(e, current_user_id) for e in result.scalars().all()]

    # --- Présence ---

    async def upsert_presence(
        self, analysis_id: uuid.UUID, *, user_id: str, name: str, element_id: uuid.UUID | None, mode: str
    ) -> None:
        now = datetime.now(UTC)
        row = await self.db.get(AnalysisPresence, (analysis_id, user_id), populate_existing=True)
        if row is None:
            self.db.add(
                AnalysisPresence(
                    analysis_id=analysis_id,
                    user_id=user_id,
                    display_name=name,
                    element_id=element_id,
                    mode=mode,
                    updated_at=now,
                )
            )
        else:
            row.display_name, row.element_id, row.mode, row.updated_at = name, element_id, mode, now
        # Ménage : les présences périmées de cette analyse ne servent plus à rien.
        await self.db.execute(
            delete(AnalysisPresence).where(
                AnalysisPresence.analysis_id == analysis_id,
                AnalysisPresence.updated_at < now - timedelta(seconds=settings.PRESENCE_TTL_SECONDS * 4),
            )
        )
        await self.db.commit()

    async def remove_presence(self, analysis_id: uuid.UUID, *, user_id: str) -> None:
        await self.db.execute(
            delete(AnalysisPresence).where(
                AnalysisPresence.analysis_id == analysis_id, AnalysisPresence.user_id == user_id
            )
        )
        await self.db.commit()

    async def list_presence(self, analysis_id: uuid.UUID) -> list[PresenceOut]:
        cutoff = datetime.now(UTC) - timedelta(seconds=settings.PRESENCE_TTL_SECONDS)
        result = await self.db.execute(
            select(AnalysisPresence)
            .where(AnalysisPresence.analysis_id == analysis_id, AnalysisPresence.updated_at > cutoff)
            .execution_options(populate_existing=True)
        )
        return [
            PresenceOut(
                user_id=p.user_id,
                display_name=p.display_name,
                element_id=p.element_id,
                mode=p.mode,
                updated_at=p.updated_at,
            )
            # Le nom est chiffré en base : le tri se fait ici.
            for p in sorted(result.scalars().all(), key=lambda p: (sort_key(p.display_name), p.user_id))
        ]

    async def snapshot(self, analysis_id: uuid.UUID, *, current_user_id: str) -> LiveSnapshot:
        return LiveSnapshot(
            presence=await self.list_presence(analysis_id),
            locks=await self.list_locks(analysis_id, current_user_id=current_user_id),
        )


def lock_out(element: AnalysisElement, current_user_id: str) -> LockOut:
    return LockOut(
        element_id=element.id,
        locked_by=element.locked_by or "",
        locked_by_name=element.locked_by_name,
        locked_until=element.locked_until,
        held_by_me=element.locked_by == current_user_id,
    )
