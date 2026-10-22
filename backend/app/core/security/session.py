import json
import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass

from keycloak import KeycloakOpenID
from redis import Redis

PENDING_PREFIX = "millefeuille:auth:pending:"
SESSION_PREFIX = "millefeuille:auth:session:"
# Dernière session ouverte par une personne : permet au backend d'agir pour elle sans cookie (ex. appeler un serveur MCP
# pour un run lancé depuis le worker, voir services/tools/identity_tokens.py).
USER_SESSION_PREFIX = "millefeuille:auth:user-session:"
REFRESH_LOCK_PREFIX = "millefeuille:auth:refresh-lock:"
REFRESH_LOCK_SECONDS = 10
RATE_LIMIT_PREFIX = "millefeuille:auth:rate:"
PENDING_TTL_SECONDS = 600
# Refresh the access token this many seconds before it actually expires, so a
# request never races a token that dies mid-flight.
REFRESH_MARGIN_SECONDS = 30


@dataclass
class PendingAuth:
    code_verifier: str
    next_path: str


@dataclass
class Session:
    identity: dict
    access_token: str
    refresh_token: str
    expires_at: float
    # Needed for a silent RP-initiated logout (id_token_hint): without it,
    # Keycloak can't tell the /logout request apart from a CSRF attempt and
    # falls back to showing its own "do you want to log out?" confirmation
    # page instead of redirecting straight back to the app.
    id_token: str | None = None


class SessionStore:
    def __init__(self, redis_client: Redis, keycloak_openid: KeycloakOpenID, ttl_seconds: int) -> None:
        self._redis = redis_client
        self._keycloak_openid = keycloak_openid
        self._ttl_seconds = ttl_seconds

    def save_pending(self, state: str, pending: PendingAuth) -> None:
        self._redis.set(f"{PENDING_PREFIX}{state}", json.dumps(asdict(pending)), ex=PENDING_TTL_SECONDS)

    def pop_pending(self, state: str) -> PendingAuth | None:
        key = f"{PENDING_PREFIX}{state}"
        raw = self._redis.getdel(key)
        if not raw:
            return None
        return PendingAuth(**json.loads(raw))

    def create_session(self, identity: dict, token_response: dict) -> str:
        session_id = secrets.token_urlsafe(32)
        session = Session(
            identity=identity,
            access_token=token_response["access_token"],
            refresh_token=token_response["refresh_token"],
            expires_at=time.time() + token_response["expires_in"],
            id_token=token_response.get("id_token"),
        )
        self._redis.set(f"{SESSION_PREFIX}{session_id}", json.dumps(asdict(session)), ex=self._ttl_seconds)
        user_id = identity.get("user_id")
        if user_id:
            self._redis.set(f"{USER_SESSION_PREFIX}{user_id}", session_id, ex=self._ttl_seconds)
        return session_id

    def access_token_for_user(self, user_id: str) -> str | None:
        """Jeton d'accès frais de la dernière session d'une personne, ou None si elle n'en a plus (déconnectée,
        session expirée, jeton de renouvellement révoqué). Ne sert qu'au backend : le jeton ne sort jamais vers le
        worker ni vers le navigateur."""
        session_id = self._redis.get(f"{USER_SESSION_PREFIX}{user_id}")
        session = self.get_session(session_id) if session_id else None
        return session.access_token if session else None

    def get_session(self, session_id: str) -> Session | None:
        raw = self._redis.get(f"{SESSION_PREFIX}{session_id}")
        if not raw:
            return None

        session = Session(**json.loads(raw))
        if session.expires_at - REFRESH_MARGIN_SECONDS > time.time():
            return session

        return self._refresh_session(session_id, session)

    def _refresh_session(self, session_id: str, session: Session) -> Session | None:
        # Keycloak fait tourner le jeton de renouvellement : deux renouvellements simultanés (appels d'outils en
        # parallèle) feraient échouer le second, et on supprimerait alors la session. Un seul renouvelle ; l'autre
        # attend, puis relit la session déjà renouvelée.
        with self._refresh_lock(session_id):
            raw = self._redis.get(f"{SESSION_PREFIX}{session_id}")
            if not raw:
                return None
            current = Session(**json.loads(raw))
            if current.expires_at - REFRESH_MARGIN_SECONDS > time.time():
                return current
            return self._renew(session_id, current)

    @contextmanager
    def _refresh_lock(self, session_id: str) -> Iterator[None]:
        """Verrou court par session (`SET NX EX`, sans script Lua). Un verrou resté pris expire seul : on n'attend
        jamais plus longtemps que sa durée."""
        key = f"{REFRESH_LOCK_PREFIX}{session_id}"
        deadline = time.monotonic() + REFRESH_LOCK_SECONDS
        while not self._redis.set(key, "1", nx=True, ex=REFRESH_LOCK_SECONDS) and time.monotonic() < deadline:
            time.sleep(0.05)
        try:
            yield
        finally:
            self._redis.delete(key)

    def _renew(self, session_id: str, session: Session) -> Session | None:
        try:
            token_response = self._keycloak_openid.refresh_token(session.refresh_token)
        except Exception:
            self.delete_session(session_id)
            return None

        session.access_token = token_response["access_token"]
        session.refresh_token = token_response["refresh_token"]
        session.expires_at = time.time() + token_response["expires_in"]
        session.id_token = token_response.get("id_token", session.id_token)
        self._redis.set(f"{SESSION_PREFIX}{session_id}", json.dumps(asdict(session)), ex=self._ttl_seconds)
        return session

    def delete_session(self, session_id: str) -> None:
        self._redis.delete(f"{SESSION_PREFIX}{session_id}")

    def check_rate_limit(self, key: str, limit: int, window_seconds: int) -> bool:
        """Returns True if the call is allowed, False if the limit was hit."""
        redis_key = f"{RATE_LIMIT_PREFIX}{key}"
        count = self._redis.incr(redis_key)
        if count == 1:
            self._redis.expire(redis_key, window_seconds)
        return count <= limit
