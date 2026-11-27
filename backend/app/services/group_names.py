"""Les accès désignent un groupe par son identifiant ; on l'affiche et on le journalise par son nom."""

import uuid
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_group import AppGroup


def _as_uuid(key: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(key)
    except ValueError:
        return None


async def group_names(db: AsyncSession, keys: Collection[str]) -> dict[str, str]:
    """Noms des groupes de l'application parmi ces identifiants ; les autres sont absents du résultat."""
    ids = {key: parsed for key in keys if (parsed := _as_uuid(key))}
    if not ids:
        return {}
    rows = await db.execute(select(AppGroup.id, AppGroup.name).where(AppGroup.id.in_(list(ids.values()))))
    names = {group_id: name for group_id, name in rows}
    return {key: names[parsed] for key, parsed in ids.items() if parsed in names}


async def group_labels(db: AsyncSession, keys: Collection[str]) -> list[str]:
    """Pour le journal : le nom de chaque groupe, ou la valeur elle-même si ce n'en est pas un."""
    names = await group_names(db, keys)
    return [names.get(key, key) for key in keys]
