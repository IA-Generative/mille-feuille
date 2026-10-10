"""Schémas des notes internes d'un dossier (issue #117). Jamais exposés côté usager (#96)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class NoteCreateIn(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class NoteUpdateIn(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class NoteRestoreIn(BaseModel):
    version_id: uuid.UUID


class NoteOut(BaseModel):
    """Une note avec son contenu actuel (dernière version)."""

    id: uuid.UUID
    dossier_id: uuid.UUID
    created_by: str
    archived: bool
    content: str
    version_number: int
    last_author_id: str
    created_at: datetime
    updated_at: datetime
    # Analyse de la note par le worker pour proposer des mises à jour.
    analysis_status: str | None
    analysis_version_number: int | None
    analysis_proposal_count: int | None
    analysis_error: str | None


class NoteVersionOut(BaseModel):
    id: uuid.UUID
    note_id: uuid.UUID
    version_number: int
    content: str
    author_id: str
    restored_from_version_id: uuid.UUID | None
    created_at: datetime


class InternalNoteOut(BaseModel):
    """Note pour le worker : contenu actuel et demandeur de l'analyse."""

    id: uuid.UUID
    dossier_id: uuid.UUID
    content: str
    version_number: int
    archived: bool
    analysis_requested_by: str | None


class InternalNoteCreateIn(BaseModel):
    """Note déposée par le chat du dossier pour le compte d'une personne : ``author`` est la personne qui l'a
    demandée, préfixée par l'origine (``chat-agent:<id>``), comme les propositions."""

    content: str = Field(min_length=1, max_length=20000)
    author: str = Field(min_length=1, max_length=255)


class InternalNoteAnalysisIn(BaseModel):
    status: str = Field(pattern="^(terminé|échec)$")
    proposal_count: int | None = Field(default=None, ge=0)
    error: str | None = Field(default=None, max_length=2000)
