"""Password hashing and verification.

Uses PBKDF2-HMAC-SHA256 from the standard library so we don't add a
dependency for an MVP feature. Iteration count tracks OWASP 2024
guidance; the stored format is self-describing
(`pbkdf2_sha256$<iters>$<salt_hex>$<digest_hex>`) so rotating to a
stronger hash later is a per-row migration on next login.
"""
from __future__ import annotations

import hashlib
import hmac
import os

_ALGO = "pbkdf2_sha256"
_DEFAULT_ITERATIONS = 480_000
_KEY_LENGTH = 32
_SALT_LENGTH = 16


def hash_password(
    password: str, *, iterations: int = _DEFAULT_ITERATIONS
) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    salt = os.urandom(_SALT_LENGTH)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=_KEY_LENGTH,
    )
    return f"{_ALGO}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(stored: str, password: str) -> bool:
    if not stored or not password:
        return False
    try:
        algo, iters_s, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algo != _ALGO:
        return False
    try:
        iters = int(iters_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iters,
        dklen=len(expected),
    )
    return hmac.compare_digest(candidate, expected)


def needs_rehash(
    stored: str, *, target_iterations: int = _DEFAULT_ITERATIONS
) -> bool:
    """Return True if `stored` was hashed with weaker parameters than current.

    Callers can rehash + persist on next successful login to upgrade
    older rows transparently.
    """
    try:
        algo, iters_s, _salt_hex, _digest_hex = stored.split("$")
    except ValueError:
        return True
    if algo != _ALGO:
        return True
    try:
        return int(iters_s) < target_iterations
    except ValueError:
        return True
