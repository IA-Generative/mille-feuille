"""Reprise des groupes Keycloak dans les groupes de l'application (issue #663), appelée par la migration.

Pour chaque chemin **utilisé** (dossier, serveur d'outils, source de connaissances, partage d'analyse) : un groupe de
l'application, avec comme « Instructeur » les personnes que l'annuaire connaît dans ce groupe. Les références sont
remplacées par l'identifiant du groupe. Le journal des dossiers garde les anciens chemins."""

import json
import uuid

import sqlalchemy as sa

from app.core.crypto import decrypt, email_index, encrypt
from app.services.permissions import INSTRUCTOR_ROLE_ID

JSON_GROUP_TABLES = ("tool_servers", "knowledge_sources")


def _used_paths(connection: sa.Connection) -> list[str]:
    queries = [
        "SELECT group_id FROM dossier_group_access",
        "SELECT keycloak_group FROM analyse_shares WHERE keycloak_group IS NOT NULL",
        *(f"SELECT jsonb_array_elements_text(groups) FROM {table}" for table in JSON_GROUP_TABLES),
    ]
    found = set(connection.execute(sa.text(" UNION ".join(queries))).scalars())
    already = {str(group_id) for group_id in connection.execute(sa.text("SELECT id FROM app_groups")).scalars()}
    return sorted(path for path in found - already if path)


def _free_name(path: str, taken: set[str]) -> str:
    """« /service-culture » → « service-culture » ; le chemin entier, puis numéroté, si ce nom est pris."""
    candidates = [path.strip("/") or path, path]
    number = 2
    while True:
        for name in candidates:
            if name.lower() not in taken:
                taken.add(name.lower())
                return name
        candidates = [f"{path} ({number})"]
        number += 1


def _directory(connection: sa.Connection) -> list[tuple[str, str, list[str]]]:
    rows = connection.execute(sa.text("SELECT user_id, email, groups FROM app_users ORDER BY user_id"))
    return [(user_id, decrypt(email or ""), list(groups or [])) for user_id, email, groups in rows]


def _add_members(connection: sa.Connection, group_id: str, people: list[tuple[str, str]]) -> None:
    seen: set[str] = set()
    for user_id, email in people:
        address = email.strip().lower()
        index = email_index(address) if address else None
        if index in seen:  # deux comptes pour une même adresse : le second n'est repris que par son compte
            address, index = "", None
        if index:
            seen.add(index)
        values = {
            "id": uuid.uuid4(),
            "group": group_id,
            "role": INSTRUCTOR_ROLE_ID,
            "user": user_id,
            "email": encrypt(address) if address else None,
            "index": index,
        }
        connection.execute(
            sa.text(
                "INSERT INTO app_group_members (id, group_id, role_id, user_id, email, email_index) "
                "VALUES (:id, :group, :role, :user, :email, :index)"
            ),
            values,
        )
        connection.execute(
            sa.text(
                "INSERT INTO app_group_events (id, group_id, type, subject_user_id, subject_email, role_name) "
                "VALUES (:id, :group, 'member_added', :user, :email, 'Instructeur')"
            ),
            {**values, "id": uuid.uuid4()},
        )


def _replace_references(connection: sa.Connection, mapping: dict[str, str]) -> None:
    for old, new in mapping.items():
        for statement in (
            "UPDATE dossier_group_access SET group_id = :new WHERE group_id = :old",
            "UPDATE analyse_shares SET keycloak_group = :new WHERE keycloak_group = :old",
        ):
            connection.execute(sa.text(statement), {"old": old, "new": new})
    for table in JSON_GROUP_TABLES:
        for row_id, groups in connection.execute(sa.text(f"SELECT id, groups FROM {table}")).all():
            replaced = [mapping.get(group, group) for group in groups or []]
            if replaced != list(groups or []):
                connection.execute(
                    sa.text(f"UPDATE {table} SET groups = CAST(:groups AS jsonb) WHERE id = :id"),
                    {"groups": json.dumps(replaced), "id": row_id},
                )


def _set_directory_groups(connection: sa.Connection, user_id: str, groups: list[str]) -> None:
    connection.execute(
        sa.text("UPDATE app_users SET groups = CAST(:groups AS jsonb) WHERE user_id = :user"),
        {"groups": json.dumps(groups), "user": user_id},
    )


def convert_keycloak_groups(connection: sa.Connection) -> int:
    """Renvoie le nombre de groupes créés. Peut être relancée : un chemin déjà repris n'est plus dans les références."""
    paths = _used_paths(connection)
    directory = _directory(connection)
    taken = set(connection.execute(sa.text("SELECT lower(name) FROM app_groups")).scalars())
    mapping: dict[str, str] = {}
    for path in paths:
        group_id = str(uuid.uuid4())
        connection.execute(
            sa.text(
                "INSERT INTO app_groups (id, name, description, keycloak_path) VALUES (:id, :name, :description, :path)"
            ),
            {
                "id": group_id,
                "name": _free_name(path, taken),
                "description": f"Repris du groupe Keycloak « {path} ».",
                "path": path,
            },
        )
        _add_members(connection, group_id, [(user, email) for user, email, groups in directory if path in groups])
        mapping[path] = group_id
    _replace_references(connection, mapping)
    # La copie de l'annuaire ne contient plus que des groupes de l'application dont la personne est membre.
    for user_id, _, _ in directory:
        mine = connection.execute(
            sa.text("SELECT group_id FROM app_group_members WHERE user_id = :user"), {"user": user_id}
        ).scalars()
        _set_directory_groups(connection, user_id, sorted(str(group_id) for group_id in mine))
    return len(mapping)


def restore_keycloak_groups(connection: sa.Connection) -> None:
    """Retour en arrière : remet les chemins et retire les groupes repris."""
    rows = connection.execute(sa.text("SELECT id, keycloak_path FROM app_groups WHERE keycloak_path IS NOT NULL")).all()
    mapping = {str(group_id): path for group_id, path in rows}
    for user_id, _, groups in _directory(connection):
        if any(group in mapping for group in groups):
            _set_directory_groups(connection, user_id, [mapping.get(group, group) for group in groups])
    _replace_references(connection, mapping)
    for group_id in mapping:
        connection.execute(sa.text("DELETE FROM app_groups WHERE id = :id"), {"id": group_id})
