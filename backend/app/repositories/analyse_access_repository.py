"""Lire et remplacer les accès d'une analyse (issue #662), avec leur historique."""

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import email_index
from app.models.access_group import AppRole
from app.models.analyse_access import AnalyseAccessVersion, AnalyseGroup, AnalysePerson


@dataclass
class WantedPerson:
    role_id: uuid.UUID
    user_id: str | None = None
    email: str | None = None


def _key(user_id: str | None, email: str | None) -> tuple[str, str]:
    return ("user", user_id) if user_id else ("email", (email or "").lower())


class AnalyseAccessRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def group_ids(self, analyse_id: uuid.UUID) -> list[str]:
        query = select(AnalyseGroup.group_id).where(AnalyseGroup.analyse_id == analyse_id)
        return sorted(await self.db.scalars(query))

    async def people(self, analyse_id: uuid.UUID) -> Sequence[AnalysePerson]:
        query = (
            select(AnalysePerson)
            .where(AnalysePerson.analyse_id == analyse_id)
            .order_by(AnalysePerson.created_at, AnalysePerson.id)
        )
        return (await self.db.execute(query)).scalars().all()

    async def versions(self, analyse_id: uuid.UUID) -> Sequence[AnalyseAccessVersion]:
        query = (
            select(AnalyseAccessVersion)
            .where(AnalyseAccessVersion.analyse_id == analyse_id)
            .order_by(AnalyseAccessVersion.created_at.desc())
        )
        return (await self.db.execute(query)).scalars().all()

    async def roles(self) -> dict[uuid.UUID, AppRole]:
        return {role.id: role for role in await self.db.scalars(select(AppRole))}

    @staticmethod
    def read_version(version: AnalyseAccessVersion) -> tuple[list[str], list[WantedPerson]]:
        content = json.loads(version.content)
        people = [
            WantedPerson(uuid.UUID(p["role_id"]), p.get("user_id"), p.get("email")) for p in content.get("people", [])
        ]
        return content.get("group_ids", []), people

    async def replace(
        self, analyse_id: uuid.UUID, group_ids: list[str], people: list[WantedPerson], author_id: str
    ) -> None:
        """Remplace les accès en gardant l'état précédent. Sans changement, rien n'est écrit."""
        current_groups = await self.group_ids(analyse_id)
        current = {_key(p.user_id, p.email): p for p in await self.people(analyse_id)}
        wanted = {_key(p.user_id, p.email): p for p in people}
        wanted_groups = sorted(set(group_ids))
        if wanted_groups == current_groups and {k: p.role_id for k, p in wanted.items()} == {
            k: p.role_id for k, p in current.items()
        }:
            return
        previous = {
            "group_ids": current_groups,
            "people": [{"user_id": p.user_id, "email": p.email, "role_id": str(p.role_id)} for p in current.values()],
        }
        self.db.add(AnalyseAccessVersion(analyse_id=analyse_id, content=json.dumps(previous), author_id=author_id))

        for row in await self.db.scalars(select(AnalyseGroup).where(AnalyseGroup.analyse_id == analyse_id)):
            if row.group_id not in wanted_groups:
                await self.db.delete(row)
        for group_id in set(wanted_groups) - set(current_groups):
            self.db.add(AnalyseGroup(analyse_id=analyse_id, group_id=group_id, granted_by=author_id))

        for key, person in current.items():
            if key not in wanted:
                await self.db.delete(person)
            else:
                person.role_id = wanted[key].role_id
        for key, person in wanted.items():
            if key not in current:
                self.db.add(
                    AnalysePerson(
                        analyse_id=analyse_id,
                        role_id=person.role_id,
                        user_id=person.user_id,
                        email=person.email,
                        email_index=email_index(person.email) if person.email else None,
                        added_by=author_id,
                    )
                )
        await self.db.commit()
