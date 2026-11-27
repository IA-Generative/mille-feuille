"""Chiffrer les données déjà en base, ou les rechiffrer avec la clé active (migration et rotation, issue #658).

Rotation : placer la nouvelle clé **en tête** de ENCRYPTION_KEYS en gardant l'ancienne, redémarrer, lancer
``python -m app.core.data_encryption``, puis retirer l'ancienne clé."""

import asyncio
import json

import sqlalchemy as sa

from app.core.crypto import PREFIX, decrypt, email_index, encrypt, is_current

# (table, colonnes de la clé primaire, colonne chiffrée)
COLUMNS = [
    ("app_users", ("user_id",), "name"),
    ("app_users", ("user_id",), "email"),
    ("analyse_shares", ("id",), "email"),
    ("dossier_events", ("id",), "actor_name"),
    ("analysis_elements", ("id",), "locked_by_name"),
    ("analysis_presence", ("analysis_id", "user_id"), "display_name"),
    ("knowledge_sources", ("id",), "owner_name"),
    ("tool_servers", ("id",), "owner_name"),
    ("reports", ("id",), "user_display"),
    ("notifications", ("id",), "message"),
    ("app_group_members", ("id",), "email"),
    ("app_group_events", ("id",), "actor_name"),
    ("app_group_events", ("id",), "subject_email"),
]
# Tables dont une adresse a son empreinte (colonnes `email` et `email_index`).
INDEXED_EMAILS = [("app_users", "user_id"), ("app_group_members", "id")]
# Contenus du journal qui nomment une personne.
PEOPLE_EVENT_TYPE = "assignee_changed"
PEOPLE_KEYS = ("from", "to")


def _where(keys: tuple[str, ...]) -> str:
    return " AND ".join(f"{key} = :{key}" for key in keys)


def _rewrite_columns(connection: sa.Connection, transform) -> int:
    changed = 0
    # La migration du chiffrement passe avant la création des tables venues après elle.
    existing = set(sa.inspect(connection).get_table_names())
    for table, keys, column in COLUMNS:
        if table not in existing:
            continue
        selected = ", ".join((*keys, column))
        rows = connection.execute(sa.text(f"SELECT {selected} FROM {table} WHERE {column} <> ''")).mappings().all()
        for row in rows:
            value = transform(row[column])
            if value is None:
                continue
            connection.execute(
                sa.text(f"UPDATE {table} SET {column} = :value WHERE {_where(keys)}"),
                {"value": value, **{key: row[key] for key in keys}},
            )
            changed += 1
    return changed


def _rewrite_events(connection: sa.Connection, transform, *, mark: bool) -> int:
    changed = 0
    query = sa.text("SELECT id, payload FROM dossier_events WHERE type = :type")
    for row in connection.execute(query, {"type": PEOPLE_EVENT_TYPE}).mappings().all():
        payload, dirty = dict(row["payload"]), False
        for key in PEOPLE_KEYS:
            person = payload.get(key)
            if not isinstance(person, dict) or not person.get("name"):
                continue
            value = transform(person["name"])
            if value is None and (not mark or person.get("person")):
                continue
            person = {**person, "name": person["name"] if value is None else value}
            if mark:
                person["person"] = True
            else:
                person.pop("person", None)
            payload[key], dirty = person, True
        if dirty:
            connection.execute(
                sa.text("UPDATE dossier_events SET payload = CAST(:payload AS jsonb) WHERE id = :id"),
                {"payload": json.dumps(payload), "id": row["id"]},
            )
            changed += 1
    return changed


def _index_emails(connection: sa.Connection) -> None:
    existing = set(sa.inspect(connection).get_table_names())
    for table, key in INDEXED_EMAILS:
        if table not in existing:
            continue
        rows = connection.execute(sa.text(f"SELECT {key}, email FROM {table} WHERE email <> ''")).mappings().all()
        for row in rows:
            connection.execute(
                sa.text(f"UPDATE {table} SET email_index = :index WHERE {key} = :{key}"),
                {"index": email_index(decrypt(row["email"])), key: row[key]},
            )


def _to_current(value: str) -> str | None:
    """La valeur chiffrée avec la clé active, ou None si elle l'est déjà."""
    return None if value.startswith(PREFIX) and is_current(value) else encrypt(decrypt(value))


def _to_clear(value: str) -> str | None:
    return decrypt(value) if value.startswith(PREFIX) else None


def encrypt_existing(connection: sa.Connection) -> int:
    """Chiffre (ou rechiffre) tout ce qui ne l'est pas avec la clé active. Peut être relancé sans risque."""
    changed = _rewrite_columns(connection, _to_current) + _rewrite_events(connection, _to_current, mark=True)
    _index_emails(connection)
    return changed


def decrypt_existing(connection: sa.Connection) -> int:
    """Retour en arrière de la migration : tout remettre en clair."""
    return _rewrite_columns(connection, _to_clear) + _rewrite_events(connection, _to_clear, mark=False)


async def _main() -> None:
    from app.db import engine

    async with engine.begin() as connection:
        changed = await connection.run_sync(encrypt_existing)
    await engine.dispose()
    print(f"{changed} valeur(s) rechiffrée(s) avec la clé active.")


if __name__ == "__main__":
    asyncio.run(_main())
