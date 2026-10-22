"""Garde d'URL des serveurs MCP ajoutés par les utilisateurs (anti-SSRF). Deux étapes, chacune testable seule :

- `check_url_shape` : forme de l'URL (schéma, identifiants, domaine autorisé), sans réseau ;
- `check_addresses` : les adresses auxquelles le nom d'hôte se résout sont toutes publiques ;
- `ensure_safe_url` : les deux, avec la résolution DNS.

Limite connue : la vérification se fait avant la connexion, pas pendant (un nom qui change d'adresse entre-temps,
« DNS rebinding », passerait). On revérifie à chaque appel de tool pour en réduire la fenêtre."""

import asyncio
import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

from app.config import ToolSettings


class UnsafeUrlError(ValueError):
    """URL refusée ; le message est en français et affichable tel quel."""


Resolver = Callable[[str], Iterable[str]]


def _system_resolver(host: str) -> list[str]:
    try:
        return [info[4][0] for info in socket.getaddrinfo(host, None)]
    except socket.gaierror as error:
        raise UnsafeUrlError(f"L'adresse « {host} » est introuvable.") from error


def _is_allowed_domain(host: str, allowed_domains: list[str]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)


def check_url_shape(url: str, *, allowed_domains: list[str], allow_insecure: bool) -> str:
    """Renvoie l'URL normalisée (sans espaces autour), ou lève `UnsafeUrlError`."""
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise UnsafeUrlError("L'adresse doit commencer par https:// et contenir un nom de serveur.")
    if parts.scheme == "http" and not allow_insecure:
        raise UnsafeUrlError("L'adresse doit utiliser https.")
    if parts.username or parts.password:
        raise UnsafeUrlError("L'adresse ne doit pas contenir d'identifiants.")
    host = parts.hostname.lower()
    if allowed_domains and not _is_allowed_domain(host, allowed_domains):
        raise UnsafeUrlError(f"Le domaine « {host} » n'est pas autorisé par l'administrateur.")
    return url


def check_addresses(addresses: Iterable[str], *, allow_insecure: bool) -> None:
    """Refuse les adresses privées, locales, de liaison locale (dont les métadonnées cloud) et réservées."""
    if allow_insecure:
        return
    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise UnsafeUrlError("Les adresses internes, locales et privées ne sont pas autorisées.")


async def ensure_safe_url(url: str, settings: ToolSettings | None = None, resolver: Resolver | None = None) -> str:
    settings = settings or ToolSettings()
    resolver = resolver or _system_resolver
    safe_url = check_url_shape(
        url, allowed_domains=settings.allowed_domains, allow_insecure=settings.TOOL_SERVER_ALLOW_INSECURE
    )
    host = urlsplit(safe_url).hostname or ""
    # La résolution DNS est bloquante : on la sort de la boucle d'événements.
    addresses = await asyncio.to_thread(lambda: list(resolver(host)))
    check_addresses(addresses, allow_insecure=settings.TOOL_SERVER_ALLOW_INSECURE)
    return safe_url
