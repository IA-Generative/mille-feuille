import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.core import crypto
from app.core.data_encryption import COLUMNS, encrypt_existing
from app.core.security.factory import RequestContext
from app.db import async_session_factory, engine
from app.models import AppGroupEventType, Base
from app.models.encrypted import EncryptedString
from app.repositories.access_group_repository import (
    AccessGroupRepository,
    AlreadyMemberError,
    InUseError,
    NameTakenError,
    SystemRoleError,
    UnknownPermissionError,
    permissions_of,
)
from app.services.permissions import GROUP_ADMIN_ROLE_ID, INSTRUCTOR_ROLE_ID, READER_ROLE_ID, Permission

ACTOR = RequestContext(
    user_id="admin-1", email="admin@example.org", roles=[], is_admin=True, first_name="Alex", last_name="Admin"
)


@pytest.fixture
def run(client: TestClient):
    """Exécute un scénario avec un dépôt, dans la boucle de l'application."""

    def _run(scenario):
        async def wrapped():
            async with async_session_factory() as db:
                return await scenario(AccessGroupRepository(db))

        return client.portal.call(wrapped)

    return _run


def _name(prefix: str) -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


def test_the_provided_roles_exist_and_the_admin_one_is_frozen(run) -> None:
    async def scenario(repository: AccessGroupRepository):
        admin = await repository.get_role(GROUP_ADMIN_ROLE_ID)
        instructor = await repository.get_role(INSTRUCTOR_ROLE_ID)
        reader = await repository.get_role(READER_ROLE_ID)
        assert permissions_of(admin) == set(Permission) == set(admin.permissions)
        assert Permission.DOSSIER_VALIDATE in permissions_of(instructor)
        assert permissions_of(reader) == {Permission.DOSSIER_VIEW}
        with pytest.raises(SystemRoleError):
            await repository.update_role(admin, name="Autre", description="", permissions=[], actor=ACTOR)
        with pytest.raises(SystemRoleError):
            await repository.delete_role(admin)

    run(scenario)


def test_a_role_keeps_its_history_and_can_be_restored(run) -> None:
    async def scenario(repository: AccessGroupRepository):
        name = _name("Rôle")
        role = await repository.create_role(name=name, description="", permissions=["dossier.view"], actor=ACTOR)
        role_id = role.id  # un nom refusé annule la transaction : les objets chargés sont périmés
        with pytest.raises(UnknownPermissionError):
            await repository.create_role(name=_name("Rôle"), description="", permissions=["tout"], actor=ACTOR)
        with pytest.raises(NameTakenError):
            await repository.create_role(name=name.upper(), description="", permissions=[], actor=ACTOR)

        role = await repository.get_role(role_id)
        role = await repository.update_role(
            role, name=name, description="", permissions=["dossier.edit", "dossier.view"], actor=ACTOR
        )
        assert [v.field for v in role.versions] == ["permissions"]
        assert role.versions[0].author_id == "admin-1"
        role = await repository.restore_role(role, role.versions[0].id, ACTOR)
        assert role.permissions == ["dossier.view"]
        assert len(role.versions) == 2
        await repository.delete_role(role)

    run(scenario)


def test_members_are_unique_journaled_and_block_deletion(run) -> None:
    async def scenario(repository: AccessGroupRepository):
        group = await repository.create_group(name=_name("Groupe"), description="", actor=ACTOR)
        instructor = await repository.get_role(INSTRUCTOR_ROLE_ID)
        reader = await repository.create_role(name=_name("Rôle"), description="", permissions=[], actor=ACTOR)
        group = await repository.get_group(group.id)

        member = await repository.add_member(group, reader, email=" Camille@Example.org ", actor=ACTOR)
        assert (member.email, member.user_id) == ("camille@example.org", None)
        with pytest.raises(AlreadyMemberError):
            await repository.add_member(group, instructor, email="CAMILLE@example.org", actor=ACTOR)
        known = await repository.add_member(group, instructor, user_id="u-42", actor=ACTOR)
        with pytest.raises(AlreadyMemberError):
            await repository.add_member(group, instructor, user_id="u-42", actor=ACTOR)

        with pytest.raises(InUseError):
            await repository.delete_role(reader)
        with pytest.raises(InUseError):
            await repository.delete_group(group, ACTOR)

        await repository.set_member_role(member, instructor, ACTOR)
        await repository.remove_member(member, ACTOR)
        await repository.remove_member(known, ACTOR)
        await repository.delete_role(reader)
        await repository.delete_group(group, ACTOR)

        events = await repository.events(group.id)  # le journal survit au groupe
        assert sorted(e.type for e in events) == sorted(
            [
                AppGroupEventType.GROUP_CREATED,
                AppGroupEventType.MEMBER_ADDED,
                AppGroupEventType.MEMBER_ADDED,
                AppGroupEventType.MEMBER_ROLE_CHANGED,
                AppGroupEventType.MEMBER_REMOVED,
                AppGroupEventType.MEMBER_REMOVED,
                AppGroupEventType.GROUP_DELETED,
            ]
        )
        change = next(e for e in events if e.type == AppGroupEventType.MEMBER_ROLE_CHANGED)
        assert (change.previous_role_name, change.role_name) == (reader.name, "Instructeur")
        assert (change.actor_name, change.subject_email) == ("Alex Admin", "camille@example.org")

    run(scenario)


def test_a_group_name_is_versioned_and_addresses_are_not_stored_in_clear(run) -> None:
    async def scenario(repository: AccessGroupRepository):
        first = _name("Groupe")
        group = await repository.create_group(name=first, description="", actor=ACTOR)
        group = await repository.update_group(group, name=_name("Renommé"), description="d", actor=ACTOR)
        name_version = next(v for v in group.versions if v.field == "name")
        group = await repository.restore_group(group, name_version.id, ACTOR)
        assert (group.name, group.description) == (first, "d")

        role = await repository.get_role(READER_ROLE_ID)
        member = await repository.add_member(group, role, email="secret@example.org", actor=ACTOR)
        async with engine.connect() as connection:
            stored = await connection.scalar(
                sa.text("SELECT email || email_index FROM app_group_members WHERE id = :id"), {"id": member.id}
            )
        assert "secret" not in stored and stored.endswith(crypto.email_index("secret@example.org"))
        await repository.remove_member(member, ACTOR)

    run(scenario)


def test_every_encrypted_column_is_covered_by_the_key_rotation(client: TestClient) -> None:
    declared = {
        (table.name, column.name)
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if isinstance(column.type, EncryptedString)
    }
    assert declared == {(table, column) for table, _, column in COLUMNS}

    async def run_all() -> None:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            await connection.run_sync(encrypt_existing)  # chaque table et colonne citée existe
            await transaction.rollback()

    client.portal.call(run_all)
