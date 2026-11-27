import json
import uuid

import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.core.crypto import decrypt, encrypt
from app.db import engine
from app.services.legacy_groups import convert_keycloak_groups, restore_keycloak_groups
from app.services.permissions import INSTRUCTOR_ROLE_ID


def _legacy_data(connection: sa.Connection, path: str, member: str, outsider: str) -> str:
    for user_id, groups in ((member, [path, "/jamais-utilise"]), (outsider, ["/jamais-utilise"])):
        connection.execute(
            sa.text(
                "INSERT INTO app_users (user_id, name, email, groups, is_admin) "
                "VALUES (:id, 'x', :email, CAST(:groups AS jsonb), false)"
            ),
            {"id": user_id, "email": encrypt(f"{user_id}@example.org"), "groups": json.dumps(groups)},
        )
    dossier_id = str(uuid.uuid4())
    connection.execute(
        sa.text(
            "INSERT INTO dossiers (id, name, analyse_version, status, visibility, custom_values) "
            "VALUES (:id, 'Ancien', 'v1', 'EN_ATTENTE', 'restricted', '{}')"
        ),
        {"id": dossier_id},
    )
    connection.execute(
        sa.text("INSERT INTO dossier_group_access (dossier_id, group_id) VALUES (:d, :g)"),
        {"d": dossier_id, "g": path},
    )
    return dossier_id


def _scenario(connection: sa.Connection) -> None:
    path = f"/ancien-{uuid.uuid4().hex[:8]}"
    member, outsider = str(uuid.uuid4()), str(uuid.uuid4())
    dossier_id = _legacy_data(connection, path, member, outsider)

    def scalar(statement: str, **params):
        return connection.execute(sa.text(statement), params).scalar()

    convert_keycloak_groups(connection)

    group_id = str(scalar("SELECT id FROM app_groups WHERE keycloak_path = :p", p=path))
    assert scalar("SELECT name FROM app_groups WHERE keycloak_path = :p", p=path) == path.strip("/")
    assert scalar("SELECT group_id FROM dossier_group_access WHERE dossier_id = :d", d=dossier_id) == group_id
    rows = connection.execute(
        sa.text("SELECT user_id, role_id, email FROM app_group_members WHERE group_id = :g"), {"g": group_id}
    ).all()
    assert [(r.user_id, r.role_id, decrypt(r.email)) for r in rows] == [
        (member, INSTRUCTOR_ROLE_ID, f"{member}@example.org")
    ]
    assert scalar("SELECT groups FROM app_users WHERE user_id = :u", u=member) == [group_id]
    assert scalar("SELECT groups FROM app_users WHERE user_id = :u", u=outsider) == []
    # Un chemin qui ne sert à rien n'est pas repris.
    assert scalar("SELECT count(*) FROM app_groups WHERE keycloak_path = '/jamais-utilise'") == 0
    assert convert_keycloak_groups(connection) == 0

    restore_keycloak_groups(connection)

    assert scalar("SELECT group_id FROM dossier_group_access WHERE dossier_id = :d", d=dossier_id) == path
    assert scalar("SELECT count(*) FROM app_groups WHERE keycloak_path = :p", p=path) == 0
    assert scalar("SELECT groups FROM app_users WHERE user_id = :u", u=member) == [path]


def test_used_keycloak_groups_become_application_groups(client: TestClient) -> None:
    async def run() -> None:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.run_sync(_scenario)
            finally:
                await transaction.rollback()

    client.portal.call(run)
