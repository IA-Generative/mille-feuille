import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import DossierEventSettings
from app.models.dossier_event import DossierEvent, DossierEventType

if TYPE_CHECKING:
    from app.core.security.factory import RequestContext


@dataclass(frozen=True)
class EventActor:
    """Auteur d'un événement quand il n'y a pas de session utilisateur : l'agent assistant (MCP) agit avec
    un jeton d'application, dont on ne connaît que l'identifiant."""

    user_id: str
    name: str | None = None


def actor_of(user: "RequestContext | EventActor | None") -> tuple[str | None, str | None]:
    """(identifiant, nom affiché) de l'auteur d'un événement ; (None, None) pour une action du système."""
    if user is None:
        return None, None
    if isinstance(user, EventActor):
        return user.user_id, user.name
    name = f"{user.first_name} {user.last_name}".strip() or user.email or None
    return user.user_id, name


class DossierEventRepository:
    """Journal d'événements d'un dossier (issue #169) : **écriture et lecture seulement**. Il n'existe
    volontairement aucune méthode de modification ou de suppression."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add(
        self,
        dossier_id: uuid.UUID,
        type: DossierEventType,
        user: "RequestContext | EventActor | None" = None,
        payload: dict | None = None,
    ) -> DossierEvent:
        """Ajoute un événement à la session **sans valider** : il part dans la même transaction que l'action
        qu'il décrit (le commit de l'appelant). Pour une action du système, ``user`` reste None."""
        actor_id, actor_name = actor_of(user)
        event = DossierEvent(
            dossier_id=dossier_id, type=type.value, actor_id=actor_id, actor_name=actor_name, payload=payload or {}
        )
        self.db.add(event)
        return event

    async def record_consultation(self, dossier_id: uuid.UUID, user: "RequestContext") -> bool:
        """Enregistre une consultation, **une seule par utilisateur dans la fenêtre** (CONSULTATION_DEDUP_MINUTES).
        Renvoie False si l'une est déjà enregistrée dans la fenêtre."""
        window = timedelta(minutes=DossierEventSettings().CONSULTATION_DEDUP_MINUTES)
        recent = await self.db.scalar(
            select(func.count())
            .select_from(DossierEvent)
            .where(
                DossierEvent.dossier_id == dossier_id,
                DossierEvent.type == DossierEventType.CONSULTED.value,
                DossierEvent.actor_id == user.user_id,
                DossierEvent.created_at >= datetime.now(UTC) - window,
            )
        )
        if recent:
            return False
        self.add(dossier_id, DossierEventType.CONSULTED, user)
        await self.db.commit()
        return True

    async def record_admin_access(
        self, dossier_id: uuid.UUID, user: "RequestContext", method: str, *, write: bool
    ) -> None:
        """Trace l'entrée d'un administrateur dans un dossier restreint dont il n'est pas membre (issue #182).
        Une **modification** est tracée à chaque fois ; une **lecture** une seule fois dans la fenêtre de
        dédoublonnage des consultations."""
        if not write:
            window = timedelta(minutes=DossierEventSettings().CONSULTATION_DEDUP_MINUTES)
            recent = await self.db.scalar(
                select(func.count())
                .select_from(DossierEvent)
                .where(
                    DossierEvent.dossier_id == dossier_id,
                    DossierEvent.type == DossierEventType.ADMIN_ACCESS.value,
                    DossierEvent.actor_id == user.user_id,
                    DossierEvent.payload["write"].as_boolean().is_(False),
                    DossierEvent.created_at >= datetime.now(UTC) - window,
                )
            )
            if recent:
                return
        self.add(dossier_id, DossierEventType.ADMIN_ACCESS, user, {"method": method, "write": write})
        await self.db.commit()

    async def creator_id(self, dossier_id: uuid.UUID) -> str | None:
        """Qui a créé (déposé) le dossier : l'auteur de son événement de création ; None si le système (dossier créé
        par un connecteur) ou si le journal n'a pas cet événement."""
        return await self.db.scalar(
            select(DossierEvent.actor_id)
            .where(DossierEvent.dossier_id == dossier_id, DossierEvent.type == DossierEventType.CREATED.value)
            .order_by(DossierEvent.seq)
            .limit(1)
        )

    async def list_actors(
        self, dossier_id: uuid.UUID, *, include_admin_access: bool = False
    ) -> list[tuple[str, str | None]]:
        """Auteurs distincts d'un dossier (identifiant, dernier nom affiché), par nom : alimente le filtre « Auteur »
        de l'historique. Les actions du système (sans auteur) n'en font pas partie."""
        rows = await self.db.execute(
            select(DossierEvent.actor_id, func.max(DossierEvent.actor_name))
            .where(
                DossierEvent.dossier_id == dossier_id,
                DossierEvent.actor_id.is_not(None),
                *([] if include_admin_access else [DossierEvent.type != DossierEventType.ADMIN_ACCESS.value]),
            )
            .group_by(DossierEvent.actor_id)
        )
        return sorted(((actor_id, name) for actor_id, name in rows.all()), key=lambda a: (a[1] or a[0]).casefold())

    async def list_paginated(
        self,
        dossier_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        types: Sequence[DossierEventType] | None = None,
        actor_id: str | None = None,
        include_admin_access: bool = False,
    ) -> tuple[Sequence[DossierEvent], int]:
        """Événements d'un dossier, du plus récent au plus ancien, filtrables par type et par auteur. Les accès
        administrateur (#182) ne sont montrés qu'aux administrateurs."""
        filters = [DossierEvent.dossier_id == dossier_id]
        if not include_admin_access:
            filters.append(DossierEvent.type != DossierEventType.ADMIN_ACCESS.value)
        if types:
            filters.append(DossierEvent.type.in_([t.value for t in types]))
        if actor_id:
            filters.append(DossierEvent.actor_id == actor_id)
        total = await self.db.scalar(select(func.count()).select_from(DossierEvent).where(*filters))
        result = await self.db.execute(
            select(DossierEvent)
            .where(*filters)
            # `seq` : ordre d'écriture, même entre deux événements d'une même transaction (même created_at).
            .order_by(DossierEvent.seq.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return result.scalars().all(), total or 0
