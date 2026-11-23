from app.config import KeycloakSettings


def test_proxies_is_none_without_keycloak_proxy_url(monkeypatch) -> None:
    monkeypatch.delenv("KEYCLOAK_PROXY_URL", raising=False)
    assert KeycloakSettings(_env_file=None).proxies is None


def test_proxies_targets_keycloak_proxy_url(monkeypatch) -> None:
    monkeypatch.setenv("KEYCLOAK_PROXY_URL", "http://10.224.32.127:80")
    assert KeycloakSettings(_env_file=None).proxies == {
        "http": "http://10.224.32.127:80",
        "https": "http://10.224.32.127:80",
    }
