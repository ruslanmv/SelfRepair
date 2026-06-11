"""Secret-at-rest encryption for SelfRepair connection credentials.

Connection API keys (OllaBridge ``ob_*`` keys, GitPilot/MatrixLab tokens) are
encrypted with Fernet before being written to the SQLite database. The Fernet
key is derived from the ``SELFREPAIR_SECRET_KEY`` Space secret (falling back to
``SESSION_SECRET`` and finally a dev-only constant), so set
``SELFREPAIR_SECRET_KEY`` in the Space to make saved connections survive across
worker restarts within a running container.

Golden rule: this Space never stores ``HF_TOKEN``. Only OllaBridge holds the
provider token; SelfRepair stores ``ob_*`` gateway keys and service URLs.
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _key() -> bytes:
    secret = (
        os.environ.get("SELFREPAIR_SECRET_KEY")
        or os.environ.get("SESSION_SECRET")
        or "selfrepair-dev-insecure-key-change-me"
    )
    # Derive a stable 32-byte urlsafe key from the secret.
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


def encrypt(plaintext: str) -> str:
    """Encrypt a secret. Empty input returns empty string."""
    if not plaintext:
        return ""
    return Fernet(_key()).encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a stored secret. Returns "" if undecryptable (e.g. key rotated)."""
    if not token:
        return ""
    try:
        return Fernet(_key()).decrypt(token.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        return ""


def mask(secret: str) -> str:
    """Render a secret for display without exposing it."""
    if not secret:
        return ""
    if len(secret) <= 10:
        return "••••••"
    return f"{secret[:6]}…{secret[-4:]}"
