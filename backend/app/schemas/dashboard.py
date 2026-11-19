import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.work_slot import SlotOut


class DashboardStatsOut(BaseModel):
    """Indicateurs personnels : les dossiers affectés à la personne."""

    total_dossiers: int
    closed_dossiers: int
    # Clôturés cette semaine (lundi à dimanche, heure de Paris) et la semaine précédente.
    completed_this_week: int
    completed_prev_week: int
    # Clôturés par semaine sur les 4 dernières semaines, la plus ancienne d'abord.
    weekly_closed: list[int]
    # Délai moyen, en jours, entre l'arrivée d'un dossier et sa clôture (0 s'il n'y en a pas).
    avg_processing_days: float
    # Part des dossiers clos au plus tard le jour de leur échéance, entre 0 et 1 (0 s'il n'y en a pas).
    on_time_rate: float


class DashboardUrgencyOut(BaseModel):
    dossier_id: uuid.UUID
    dossier_name: str
    analyse_id: uuid.UUID
    analyse_name: str
    status_label: str | None
    due_at: date
    # Niveau calculé selon les seuils de l'analyse (#172) : proche ou dépassée.
    level: Literal["soon", "overdue"]
    days_left: int
    color: str | None
    # Mon créneau de traitement sur ce dossier, s'il y en a un (privé : jamais celui d'un autre).
    slot: SlotOut | None = None


class DashboardOtherOut(BaseModel):
    """Dossier ouvert qui n'est pas une urgence (échéance lointaine ou absente) : il reste planifiable dans l'agenda."""

    dossier_id: uuid.UUID
    dossier_name: str
    analyse_id: uuid.UUID
    analyse_name: str
    status_label: str | None
    due_at: date | None
    slot: SlotOut | None = None


class DashboardStatusCountOut(BaseModel):
    status_id: uuid.UUID
    label: str
    # Les statuts sont propres à chaque analyse : deux analyses peuvent avoir un « À instruire ».
    analyse_name: str
    count: int


class DashboardUnassignedOut(BaseModel):
    dossier_id: uuid.UUID
    dossier_name: str
    analyse_name: str
    created_at: datetime


class DashboardActivityOut(BaseModel):
    id: uuid.UUID
    kind: Literal["status_changed", "document_added", "analysis_done", "analysis_failed"]
    dossier_id: uuid.UUID
    dossier_name: str
    message: str
    at: datetime


class DashboardOut(BaseModel):
    stats: DashboardStatsOut
    urgencies: list[DashboardUrgencyOut]
    # Mes autres dossiers ouverts (ni proches ni dépassés, ou sans échéance), pour les planifier aussi.
    others: list[DashboardOtherOut]
    status_counts: list[DashboardStatusCountOut]
    # ``null`` : la personne n'a pas le droit de voir les dossiers non affectés.
    unassigned: list[DashboardUnassignedOut] | None
    activity: list[DashboardActivityOut]
