"""Chiffrement applicatif (AES-256-GCM) des données personnelles : la clé ne passe jamais dans les requêtes SQL.

Une valeur chiffrée s'écrit ``enc:v1:<identifiant de clé>:<base64(nonce + texte chiffré)>``. Une valeur sans ce
préfixe est rendue telle quelle : c'est une donnée pas encore reprise par la migration."""

import base64
import binascii
import hashlib
import hmac
import os
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import EncryptionSettings

PREFIX = "enc:v1:"
KEY_BYTES = 32
NONCE_BYTES = 12


class EncryptionError(RuntimeError):
    """Configuration absente ou invalide, ou valeur illisible avec les clés fournies."""


def _decode_key(value: str, label: str) -> bytes:
    try:
        key = base64.b64decode(value.strip(), validate=True)
    except (binascii.Error, ValueError) as error:
        raise EncryptionError(f"{label} : la clé n'est pas en base64") from error
    if len(key) != KEY_BYTES:
        raise EncryptionError(f"{label} : la clé doit faire {KEY_BYTES} octets")
    return key


@lru_cache
def _keys() -> tuple[str, dict[str, bytes]]:
    """(identifiant de la clé active, clés par identifiant)."""
    entries = [entry for entry in EncryptionSettings().ENCRYPTION_KEYS.split(",") if entry.strip()]
    if not entries:
        raise EncryptionError("ENCRYPTION_KEYS n'est pas renseignée")
    keys: dict[str, bytes] = {}
    for entry in entries:
        key_id, separator, value = entry.strip().partition(":")
        if not separator or not key_id or key_id in keys:
            raise EncryptionError("ENCRYPTION_KEYS : format attendu « identifiant:clé », identifiants distincts")
        keys[key_id] = _decode_key(value, f"ENCRYPTION_KEYS ({key_id})")
    return next(iter(keys)), keys


@lru_cache
def _index_key() -> bytes:
    value = EncryptionSettings().EMAIL_INDEX_KEY
    if not value:
        raise EncryptionError("EMAIL_INDEX_KEY n'est pas renseignée")
    return _decode_key(value, "EMAIL_INDEX_KEY")


def check_configuration() -> None:
    """Au démarrage : mieux vaut refuser de démarrer qu'échouer à la première connexion."""
    _keys()
    _index_key()


def reset_cache() -> None:
    """Relire les clés (rotation, tests)."""
    _keys.cache_clear()
    _index_key.cache_clear()


def is_current(value: str) -> bool:
    return value.startswith(f"{PREFIX}{_keys()[0]}:")


def encrypt(value: str) -> str:
    key_id, keys = _keys()
    nonce = os.urandom(NONCE_BYTES)
    sealed = AESGCM(keys[key_id]).encrypt(nonce, value.encode(), key_id.encode())
    return f"{PREFIX}{key_id}:{base64.b64encode(nonce + sealed).decode()}"


def decrypt(value: str) -> str:
    if not value.startswith(PREFIX):
        return value
    key_id, _, payload = value.removeprefix(PREFIX).partition(":")
    key = _keys()[1].get(key_id)
    if key is None:
        raise EncryptionError(f"Aucune clé « {key_id} » dans ENCRYPTION_KEYS")
    try:
        raw = base64.b64decode(payload, validate=True)
        return AESGCM(key).decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], key_id.encode()).decode()
    except (InvalidTag, binascii.Error, ValueError) as error:
        raise EncryptionError(f"Valeur illisible avec la clé « {key_id} »") from error


def email_index(email: str) -> str:
    """Empreinte d'une adresse (casse et espaces ignorés) : la retrouver exactement sans la déchiffrer."""
    return hmac.new(_index_key(), email.strip().lower().encode(), hashlib.sha256).hexdigest()
