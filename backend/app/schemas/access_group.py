"""Groupes, rôles et membres (issue #661)."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.services.permissions import Permission

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]


class AccessVersionOut(BaseModel):
    """L'ancienne valeur d'un champ (« name », « description » ou « permissions »)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    field: str
    content: str | list[str]
    created_at: datetime


class GroupIn(BaseModel):
    name: Name
    description: Description = ""


class GroupOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    member_count: int
    can_manage_members: bool
    # Un rôle de la personne dans ce groupe permet d'y créer des analyses.
    can_create_analyses: bool
    # Sans membre et sans rien qui s'y réfère.
    deletable: bool
    versions: list[AccessVersionOut]


class GroupName(BaseModel):
    id: str
    name: str


class MemberIn(BaseModel):
    """Une personne connue (`user_id`, choisie dans l'annuaire) ou une adresse."""

    email: Email | None = None
    user_id: Annotated[str, StringConstraints(max_length=100)] | None = None
    role_id: uuid.UUID

    @model_validator(mode="after")
    def _one_identity(self) -> "MemberIn":
        if (self.email is None) == (self.user_id is None):
            raise ValueError("Donnez soit une adresse, soit une personne")
        return self


class MemberRoleIn(BaseModel):
    role_id: uuid.UUID


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: str | None
    name: str
    email: str
    role_id: uuid.UUID
    # Pas encore rattachée à un compte.
    pending: bool
    # La personne connectée peut changer ou retirer ce membre.
    editable: bool


class GroupEventOut(BaseModel):
    id: uuid.UUID
    type: str
    created_at: datetime
    actor_name: str | None
    subject: str | None
    role_name: str | None
    previous_role_name: str | None


class RoleIn(BaseModel):
    name: Name
    description: Description = ""
    permissions: Annotated[list[Permission], Field(min_length=1)]


class RoleOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    permissions: list[Permission]
    system: bool
    in_use: bool
    # La personne connectée peut l'attribuer dans le groupe demandé (`?group_id=`).
    assignable: bool
    versions: list[AccessVersionOut]
