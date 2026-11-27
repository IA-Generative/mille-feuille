import base64
import json
import uuid
from collections.abc import Iterator
from unittest.mock import MagicMock

import fakeredis
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.core import crypto
from app.core.data_encryption import decrypt_existing, encrypt_existing
from app.core.security.factory import RequestContext, get_current_user
from app.core.security.session import SESSION_PREFIX, SessionStore
from app.db import engine
from app.main import app

NEW_KEY = base64.b64encode(b"n" * 32).decode()


@pytest.fixture
def keys(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    yield monkeypatch
    monkeypatch.undo()
    crypto.reset_cache()


def _use_keys(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("ENCRYPTION_KEYS", value)
    crypto.reset_cache()


def test_round_trip_with_a_fresh_nonce_each_time() -> None:
    first, second = crypto.encrypt("Éloïse Martin"), crypto.encrypt("Éloïse Martin")

    assert first != second
    assert "Martin" not in first
    assert crypto.decrypt(first) == crypto.decrypt(second) == "Éloïse Martin"
    assert crypto.decrypt("pas encore chiffré") == "pas encore chiffré"


def test_rotation_reads_the_old_key_and_writes_the_new_one(keys: pytest.MonkeyPatch) -> None:
    old = crypto.encrypt("Camille")
    current = crypto.EncryptionSettings().ENCRYPTION_KEYS

    _use_keys(keys, f"next:{NEW_KEY},{current}")
    assert crypto.decrypt(old) == "Camille"
    assert crypto.encrypt("Camille").startswith("enc:v1:next:")

    _use_keys(keys, f"next:{NEW_KEY}")
    with pytest.raises(crypto.EncryptionError):
        crypto.decrypt(old)


@pytest.mark.parametrize("value", ["", "sans-identifiant", "k:pas-du-base64!", "k:dHJvcCBjb3VydA=="])
def test_a_missing_or_invalid_key_is_refused(keys: pytest.MonkeyPatch, value: str) -> None:
    _use_keys(keys, value)

    with pytest.raises(crypto.EncryptionError):
        crypto.check_configuration()


def test_email_index_ignores_case_and_spaces() -> None:
    assert crypto.email_index(" Camille@Example.org ") == crypto.email_index("camille@example.org")
    assert crypto.email_index("camille@example.org") != crypto.email_index("sacha@example.org")


def test_a_session_is_not_readable_in_redis() -> None:
    redis = fakeredis.FakeRedis(decode_responses=True)
    store = SessionStore(redis_client=redis, keycloak_openid=MagicMock(), ttl_seconds=3600)
    identity = {"user_id": "u1", "email": "camille@example.org", "roles": [], "is_admin": False}

    session_id = store.create_session(identity, {"access_token": "jeton", "refresh_token": "rt", "expires_in": 3600})

    raw = redis.get(f"{SESSION_PREFIX}{session_id}")
    assert "camille" not in raw and "jeton" not in raw
    assert store.get_session(session_id).identity == identity


def test_a_session_sealed_with_a_removed_key_asks_to_sign_in_again(keys: pytest.MonkeyPatch) -> None:
    store = SessionStore(
        redis_client=fakeredis.FakeRedis(decode_responses=True), keycloak_openid=MagicMock(), ttl_seconds=3600
    )
    session_id = store.create_session(
        {"user_id": "u1"}, {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
    )

    _use_keys(keys, f"next:{NEW_KEY}")

    assert store.get_session(session_id) is None


async def _scalar(statement: str, **params):
    async with engine.connect() as connection:
        return await connection.scalar(sa.text(statement), params)


def _sign_in(client: TestClient, first_name: str, email: str) -> str:
    user_id = str(uuid.uuid4())
    app.dependency_overrides[get_current_user] = lambda: RequestContext(
        user_id=user_id,
        email=email,
        roles=[],
        is_admin=False,
        first_name=first_name,
        last_name="Chiffré",
        groups=["/dev-tests"],
    )
    try:
        assert client.get("/api/auth/me").status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    return user_id


def test_the_directory_is_encrypted_yet_searchable_and_sorted(client: TestClient) -> None:
    marker = uuid.uuid4().hex[:8]
    zoe = _sign_in(client, f"Zoé{marker}", f"zoe.{marker}@example.org")
    elodie = _sign_in(client, f"Élodie{marker}", f"elodie.{marker}@example.org")

    stored = client.portal.call(
        lambda: _scalar("SELECT name || ' ' || email FROM app_users WHERE user_id = :id", id=zoe)
    )
    assert marker not in stored and stored.count("enc:v1:") == 2
    index = client.portal.call(lambda: _scalar("SELECT email_index FROM app_users WHERE user_id = :id", id=zoe))
    assert index == crypto.email_index(f"zoe.{marker}@example.org")

    found = client.get("/api/users", params={"q": marker.upper()}).json()
    assert [p["id"] for p in found] == [elodie, zoe]
    assert found[0]["name"] == f"Élodie{marker} Chiffré"
    assert [p["id"] for p in client.get("/api/users", params={"q": f"zoe.{marker}@"}).json()] == [zoe]


def test_the_journal_keeps_no_name_in_clear(client: TestClient) -> None:
    marker = uuid.uuid4().hex[:8]
    person = _sign_in(client, f"Sacha{marker}", f"sacha.{marker}@example.org")
    analyse = client.post("/api/analyses", json={"name": "Chiffrement", "description": "Test"}).json()
    dossier = client.post("/api/dossiers", json={"name": "Chiffré", "analyse_id": analyse["id"]}).json()

    assert client.put(f"/api/dossiers/{dossier['id']}/assignee", json={"assignee_id": person}).status_code == 200

    stored = client.portal.call(
        lambda: _scalar(
            "SELECT payload::text FROM dossier_events WHERE dossier_id = :id AND type = 'assignee_changed'",
            id=dossier["id"],
        )
    )
    assert marker not in stored and "enc:v1:" in stored
    events = client.get(f"/api/dossiers/{dossier['id']}/events").json()["items"]
    change = next(e for e in events if e["type"] == "assignee_changed")
    assert change["payload"]["to"] == {"id": person, "name": f"Sacha{marker} Chiffré"}


def test_existing_rows_are_encrypted_and_can_be_restored(client: TestClient) -> None:
    user_id = str(uuid.uuid4())

    async def run() -> tuple:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            insert = "INSERT INTO app_users (user_id, name, email, groups, is_admin) VALUES (:id, :n, :e, '[]', false)"
            await connection.execute(sa.text(insert), {"id": user_id, "n": "Ancienne Personne", "e": "a@example.org"})
            read = sa.text("SELECT name, email, email_index FROM app_users WHERE user_id = :id")

            await connection.run_sync(encrypt_existing)
            encrypted = (await connection.execute(read, {"id": user_id})).one()
            again = await connection.run_sync(encrypt_existing)
            await connection.run_sync(decrypt_existing)
            restored = (await connection.execute(read, {"id": user_id})).one()
            await transaction.rollback()
            return encrypted, again, restored

    encrypted, again, restored = client.portal.call(run)

    assert crypto.decrypt(encrypted.name) == "Ancienne Personne" and encrypted.name != "Ancienne Personne"
    assert encrypted.email_index == crypto.email_index("a@example.org")
    assert again == 0
    assert (restored.name, restored.email) == ("Ancienne Personne", "a@example.org")


def test_people_are_marked_only_where_a_person_is_named() -> None:
    from app.models.encrypted import EncryptedPeopleJSON, person_ref

    column = EncryptedPeopleJSON()
    payload = {"to": person_ref("u1", "Camille"), "status": {"id": "s1", "name": "En cours"}}

    stored = column.process_bind_param(payload, None)

    assert "Camille" not in json.dumps(stored)
    assert stored["status"] == {"id": "s1", "name": "En cours"}
    assert column.process_result_value(stored, None)["to"] == {"id": "u1", "name": "Camille"}
