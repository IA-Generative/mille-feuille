import pytest

from app.config import TableSettings


def test_tls_verification_is_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SSL_VERIFY", raising=False)
    monkeypatch.delenv("SSL_CA_BUNDLE", raising=False)

    assert TableSettings(_env_file=None).ssl_verify is True


def test_a_ca_bundle_replaces_the_default_trust_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SSL_VERIFY", raising=False)
    monkeypatch.setenv("SSL_CA_BUNDLE", "/etc/ssl/interne.pem")

    assert TableSettings(_env_file=None).ssl_verify == "/etc/ssl/interne.pem"


def test_verification_can_be_switched_off_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SSL_VERIFY", "false")
    monkeypatch.setenv("SSL_CA_BUNDLE", "/etc/ssl/interne.pem")

    assert TableSettings(_env_file=None).ssl_verify is False
