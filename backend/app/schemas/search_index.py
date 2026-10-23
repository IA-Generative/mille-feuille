import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.search_index import IndexRebuildStatus, SearchIndexStatus


class IndexRebuildOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dossier_id: uuid.UUID
    status: IndexRebuildStatus
    target_fingerprint: str
    previous_fingerprint: str | None
    total_pages: int
    done_pages: int
    error: str | None
    requested_by: str
    created_at: datetime
    swapped_at: datetime | None
    finished_at: datetime | None


class IndexStateOut(BaseModel):
    """L'index de recherche d'un dossier, tel que l'écran le présente."""

    # `none` : pas encore d'index. `current` : à jour avec l'analyse. `obsolete` : construit avec d'autres réglages.
    freshness: Literal["none", "current", "obsolete"]
    status: SearchIndexStatus | None = None
    fingerprint: str | None = None
    # L'empreinte que donneraient les réglages actuels de l'analyse (None si elle ne se résout pas).
    expected_fingerprint: str | None = None
    problem: str | None = None
    chunk_count: int = 0
    error: str | None = None
    indexed_at: datetime | None = None
    rebuild: IndexRebuildOut | None = None


class SearchConfigOut(BaseModel):
    """Ce dont un worker a besoin pour indexer ou chercher dans un dossier."""

    dossier_id: uuid.UUID
    # Réglages effectifs de l'analyse (pour un premier index) ; None si elle ne se résout pas (voir `problem`).
    effective: dict | None = None
    fingerprint: str | None = None
    problem: str | None = None
    # L'index actif du dossier : ses réglages sont ceux à utiliser pour y écrire et y chercher.
    index_fingerprint: str | None = None
    index_settings: dict | None = None
    index_status: SearchIndexStatus | None = None
    rebuild: IndexRebuildOut | None = None
    rebuild_target_settings: dict | None = None
    rebuild_previous_settings: dict | None = None


class SearchIndexReport(BaseModel):
    """Compte rendu d'un worker sur l'index d'un dossier. Les réglages ne sont pris en compte qu'à la création de la
    ligne ou quand `replace_settings` est vrai (bascule d'une reconstruction)."""

    status: SearchIndexStatus
    chunk_count: int = 0
    error: str | None = None
    fingerprint: str | None = None
    settings: dict | None = None
    replace_settings: bool = False


class RebuildReport(BaseModel):
    status: IndexRebuildStatus | None = None
    total_pages: int | None = None
    done_pages: int | None = None
    error: str | None = None
