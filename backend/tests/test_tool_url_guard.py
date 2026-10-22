import asyncio

import pytest

from app.config import ToolSettings
from app.services.tools.url_guard import UnsafeUrlError, check_addresses, check_url_shape, ensure_safe_url


def shape(url: str, *, allowed: list[str] | None = None, insecure: bool = False) -> str:
    return check_url_shape(url, allowed_domains=allowed or [], allow_insecure=insecure)


def test_valid_https_url_is_normalized() -> None:
    assert shape("  https://mcp.example.gouv.fr/mcp ") == "https://mcp.example.gouv.fr/mcp"


@pytest.mark.parametrize(
    "url",
    ["ftp://example.org/mcp", "example.org/mcp", "https://", "http://example.org/mcp", "https://user:pw@example.org"],
)
def test_malformed_or_unsafe_shape_is_refused(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        shape(url)


def test_http_is_accepted_only_in_insecure_mode() -> None:
    assert shape("http://localhost:9000/mcp", insecure=True) == "http://localhost:9000/mcp"


def test_allowed_domains_accept_the_domain_and_its_subdomains_only() -> None:
    assert shape("https://mcp.gouv.fr/x", allowed=["gouv.fr"])
    assert shape("https://gouv.fr/x", allowed=["gouv.fr"])
    with pytest.raises(UnsafeUrlError):
        shape("https://evilgouv.fr/x", allowed=["gouv.fr"])
    with pytest.raises(UnsafeUrlError):
        shape("https://gouv.fr.evil.org/x", allowed=["gouv.fr"])


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.5", "192.168.1.10", "172.16.0.1", "169.254.169.254", "0.0.0.0", "::1", "fd00::1", "fe80::1"],
)
def test_private_local_and_metadata_addresses_are_refused(address: str) -> None:
    with pytest.raises(UnsafeUrlError):
        check_addresses([address], allow_insecure=False)


def test_one_private_address_among_public_ones_is_enough_to_refuse() -> None:
    with pytest.raises(UnsafeUrlError):
        check_addresses(["93.184.216.34", "10.0.0.1"], allow_insecure=False)


def test_public_addresses_and_insecure_mode_pass() -> None:
    check_addresses(["93.184.216.34", "2606:4700:4700::1111"], allow_insecure=False)
    check_addresses(["127.0.0.1"], allow_insecure=True)


def test_ensure_safe_url_resolves_the_host_and_checks_it() -> None:
    settings = ToolSettings(TOOL_SERVER_ALLOWED_DOMAINS="", TOOL_SERVER_ALLOW_INSECURE=False)
    ok = asyncio.run(ensure_safe_url("https://example.org/mcp", settings, resolver=lambda host: ["93.184.216.34"]))
    assert ok == "https://example.org/mcp"
    with pytest.raises(UnsafeUrlError):
        asyncio.run(ensure_safe_url("https://rebind.example.org/mcp", settings, resolver=lambda host: ["10.1.2.3"]))
