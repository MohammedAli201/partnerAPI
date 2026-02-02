# security.py
import hashlib
import secrets
from typing import Tuple

PBKDF2_ITERS = 120_000  # 100k–200k ok


def generate_api_key() -> Tuple[str, str, str]:
    """
    Returns:
        display_key: prefix.secret  (give to partner)
        prefix: first 8 chars       (store in DB)
        stored_hash: salt:hash      (store in DB)
    """
    raw = secrets.token_urlsafe(32)  # secure random

    prefix = raw[:8]
    secret_part = raw[8:]

    display_key = f"{prefix}.{secret_part}"
    full_key = prefix + secret_part  # NO DOT

    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        full_key.encode("utf-8"),
        salt,
        PBKDF2_ITERS,
    )
    stored_hash = f"{salt.hex()}:{digest.hex()}"

    return display_key, prefix, stored_hash


def validate_api_key_format(api_key: str) -> bool:
    if not api_key or "." not in api_key:
        return False
    try:
        prefix, secret = api_key.split(".", 1)
    except ValueError:
        return False
    return len(prefix) == 8 and len(secret) >= 16


def extract_prefix(api_key: str) -> str:
    return api_key.split(".", 1)[0]


def verify_api_key(api_key: str, stored_hash: str) -> bool:
    """
    api_key is prefix.secret
    stored_hash is salt_hex:hash_hex
    """
    if not validate_api_key_format(api_key):
        return False

    try:
        prefix, secret = api_key.split(".", 1)
        full_key = prefix + secret

        salt_hex, hash_hex = stored_hash.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except Exception:
        return False

    computed = hashlib.pbkdf2_hmac(
        "sha256",
        full_key.encode("utf-8"),
        salt,
        PBKDF2_ITERS,
    )
    return secrets.compare_digest(computed, expected)
