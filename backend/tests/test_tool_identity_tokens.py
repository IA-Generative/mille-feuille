import asyncio

import fakeredis
import pytest

from app.models.tool import ToolAuthMode
from app.services.tools.credentials import headers_for
from app.services.tools.credentials_errors import CredentialsUnavailableError
from app.services.tools.identity_tokens import IdentityTokens
from app.services.tools.token_exchange import ExchangedToken


class FakeSessions:
    def __init__(self, tokens: dict[str, str]) -> None:
        self.tokens = tokens

    def access_token_for_user(self, user_id: str) -> str | None:
        return self.tokens.get(user_id)


class FakeExchanger:
    def __init__(self, expires_in: int = 300, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.expires_in = expires_in
        self.error = error

    def exchange(self, subject_token: str, audience: str) -> ExchangedToken:
        self.calls.append((subject_token, audience))
        if self.error:
            raise self.error
        return ExchangedToken(access_token=f"exchanged-for-{audience}", expires_in=self.expires_in)


def make(*, sessions: dict[str, str] | None = None, exchanger: FakeExchanger | None = None):
    exchanger = exchanger or FakeExchanger()
    cache = fakeredis.FakeRedis(decode_responses=True)
    return IdentityTokens(FakeSessions(sessions or {"alice": "alice-session-token"}), exchanger, cache), exchanger


def token_for(tokens: IdentityTokens, user: str | None, audience: str | None) -> str:
    return asyncio.run(tokens.token_for(user, audience))


def test_the_session_token_is_exchanged_for_the_servers_audience() -> None:
    tokens, exchanger = make()

    assert token_for(tokens, "alice", "mcp-legifrance") == "exchanged-for-mcp-legifrance"
    assert exchanger.calls == [("alice-session-token", "mcp-legifrance")]


def test_the_exchanged_token_is_cached_per_person_and_audience() -> None:
    tokens, exchanger = make(sessions={"alice": "a", "bob": "b"})

    token_for(tokens, "alice", "mcp-1")
    token_for(tokens, "alice", "mcp-1")  # servi par le cache
    token_for(tokens, "alice", "mcp-2")  # autre audience
    token_for(tokens, "bob", "mcp-1")  # autre personne

    assert [call[1] for call in exchanger.calls] == ["mcp-1", "mcp-2", "mcp-1"]
    assert [call[0] for call in exchanger.calls] == ["a", "a", "b"]


def test_a_token_about_to_expire_is_not_cached() -> None:
    tokens, exchanger = make(exchanger=FakeExchanger(expires_in=20))

    token_for(tokens, "alice", "mcp-1")
    token_for(tokens, "alice", "mcp-1")

    assert len(exchanger.calls) == 2


@pytest.mark.parametrize(
    ("user", "audience", "code"),
    [(None, "mcp-1", "identite_absente"), ("alice", None, "audience_manquante"), ("bob", "mcp-1", "session_requise")],
)
def test_missing_identity_audience_or_session_has_a_stable_code(
    user: str | None, audience: str | None, code: str
) -> None:
    tokens, exchanger = make()

    with pytest.raises(CredentialsUnavailableError) as error:
        token_for(tokens, user, audience)

    assert error.value.code == code
    assert exchanger.calls == []


def test_a_refused_exchange_does_not_leak_keycloaks_message() -> None:
    tokens, _ = make(exchanger=FakeExchanger(error=RuntimeError("invalid_client: secret-detail")))

    with pytest.raises(CredentialsUnavailableError) as error:
        token_for(tokens, "alice", "mcp-1")

    assert error.value.code == "echange_refuse"
    assert "secret-detail" not in error.value.message


def test_headers_for_token_exchange_is_a_bearer_for_the_exchanged_token() -> None:
    tokens, _ = make()

    headers = asyncio.run(
        headers_for(ToolAuthMode.TOKEN_EXCHANGE, acting_user="alice", audience="mcp-1", identity_tokens=tokens)
    )

    assert headers == {"Authorization": "Bearer exchanged-for-mcp-1"}


def test_the_keycloak_exchanger_sends_the_token_types_keycloak_requires() -> None:
    """Gardé après un vrai échange : Keycloak refuse la demande sans `subject_token_type` (erreur 400)."""
    from unittest.mock import MagicMock

    from app.services.tools.token_exchange import ACCESS_TOKEN_TYPE, KeycloakTokenExchanger

    openid = MagicMock()
    openid.exchange_token.return_value = {"access_token": "t", "expires_in": 300}

    exchanged = KeycloakTokenExchanger(openid).exchange("subject", "mcp-1")

    openid.exchange_token.assert_called_once_with(
        "subject", audience="mcp-1", subject_token_type=ACCESS_TOKEN_TYPE, requested_token_type=ACCESS_TOKEN_TYPE
    )
    assert exchanged == ExchangedToken(access_token="t", expires_in=300)
