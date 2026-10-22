from unittest.mock import MagicMock

import fakeredis

from app.core.security.session import PendingAuth, SessionStore


def make_store(openid: MagicMock | None = None) -> SessionStore:
    return SessionStore(
        redis_client=fakeredis.FakeRedis(decode_responses=True), keycloak_openid=openid or MagicMock(), ttl_seconds=3600
    )


def test_pending_auth_round_trips_once() -> None:
    store = make_store()
    store.save_pending("state-1", PendingAuth(code_verifier="verifier", next_path="/dossiers"))

    pending = store.pop_pending("state-1")
    assert pending == PendingAuth(code_verifier="verifier", next_path="/dossiers")

    # A pending login attempt is one-time use: popping it again must fail,
    # otherwise a leaked/replayed `state` could complete a second login.
    assert store.pop_pending("state-1") is None


def test_create_and_get_session() -> None:
    store = make_store()
    identity = {"user_id": "u1", "email": "a@b.fr", "roles": [], "is_admin": False}
    token_response = {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}

    session_id = store.create_session(identity, token_response)
    session = store.get_session(session_id)

    assert session is not None
    assert session.identity == identity
    assert session.access_token == "at"


def test_get_session_returns_none_once_deleted() -> None:
    store = make_store()
    session_id = store.create_session(
        {"user_id": "u1", "email": "", "roles": [], "is_admin": False},
        {"access_token": "at", "refresh_token": "rt", "expires_in": 3600},
    )

    store.delete_session(session_id)

    assert store.get_session(session_id) is None


def test_rate_limit_allows_then_blocks() -> None:
    store = make_store()
    assert store.check_rate_limit("k", limit=2, window_seconds=60) is True
    assert store.check_rate_limit("k", limit=2, window_seconds=60) is True
    assert store.check_rate_limit("k", limit=2, window_seconds=60) is False


def test_access_token_for_user_follows_the_latest_session() -> None:
    store = make_store()
    identity = {"user_id": "u1", "email": "", "roles": [], "is_admin": False}
    store.create_session(identity, {"access_token": "first", "refresh_token": "r1", "expires_in": 3600})
    store.create_session(identity, {"access_token": "second", "refresh_token": "r2", "expires_in": 3600})

    assert store.access_token_for_user("u1") == "second"
    assert store.access_token_for_user("inconnu") is None


def test_access_token_for_user_is_none_once_the_session_is_gone() -> None:
    store = make_store()
    session_id = store.create_session(
        {"user_id": "u1", "email": "", "roles": [], "is_admin": False},
        {"access_token": "at", "refresh_token": "rt", "expires_in": 3600},
    )

    store.delete_session(session_id)

    assert store.access_token_for_user("u1") is None


def test_an_expired_access_token_is_renewed_once_and_the_new_one_is_returned() -> None:
    keycloak = MagicMock()
    keycloak.refresh_token.return_value = {"access_token": "renewed", "refresh_token": "rt2", "expires_in": 3600}
    store = make_store(keycloak)
    store.create_session(
        {"user_id": "u1", "email": "", "roles": [], "is_admin": False},
        {"access_token": "old", "refresh_token": "rt", "expires_in": 0},  # déjà expiré
    )

    assert store.access_token_for_user("u1") == "renewed"
    assert store.access_token_for_user("u1") == "renewed"  # le second appel n'a rien à renouveler
    keycloak.refresh_token.assert_called_once_with("rt")


def test_a_failed_renewal_closes_the_session() -> None:
    keycloak = MagicMock()
    keycloak.refresh_token.side_effect = RuntimeError("invalid_grant")
    store = make_store(keycloak)
    store.create_session(
        {"user_id": "u1", "email": "", "roles": [], "is_admin": False},
        {"access_token": "old", "refresh_token": "rt", "expires_in": 0},
    )

    assert store.access_token_for_user("u1") is None
