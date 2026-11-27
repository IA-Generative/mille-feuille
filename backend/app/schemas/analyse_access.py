"""Accès à une analyse (issue #662)."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.schemas.access_group import Email, GroupName


class PersonIn(BaseModel):
    """Une personne ajoutée : connue (`user_id`) ou par son adresse. `id` : une personne déjà ajoutée, qu'on garde."""

    id: uuid.UUID | None = None
    email: Email | None = None
    user_id: Annotated[str, StringConstraints(max_length=100)] | None = None
    role_id: uuid.UUID

    @model_validator(mode="after")
    def _identified(self) -> "PersonIn":
        if sum(value is not None for value in (self.id, self.email, self.user_id)) != 1:
            raise ValueError("Donnez la personne déjà ajoutée, une adresse ou une personne connue")
        return self


class AnalyseAccessIn(BaseModel):
    """L'état voulu : il **remplace** les groupes et les personnes actuels."""

    group_ids: Annotated[list[str], Field(max_length=50)]
    people: Annotated[list[PersonIn], Field(max_length=200)] = []


class AccessPersonOut(BaseModel):
    id: uuid.UUID
    name: str
    # Vide pour qui ne gère pas les accès.
    email: str
    role_id: uuid.UUID
    pending: bool
    editable: bool


class AccessGroupOut(BaseModel):
    id: str
    name: str
    # La personne connectée peut le retirer.
    editable: bool


class AccessVersionSummary(BaseModel):
    id: uuid.UUID
    created_at: datetime
    groups: list[str]
    people: list[str]


class AnalyseAccessOut(BaseModel):
    can_edit: bool
    groups: list[AccessGroupOut]
    # Les groupes que la personne peut associer.
    available_groups: list[GroupName]
    people: list[AccessPersonOut]
    assignable_role_ids: list[uuid.UUID]
    versions: list[AccessVersionSummary]
