"""Secret-at-rest encryption for SelfRepair connection credentials.

The implementation lives in ``connector_service`` so the full API and the
Hugging Face webapp derive the same Fernet key. Production must set
``SELFREPAIR_SECRET_KEY`` (or ``SESSION_SECRET``). The development fallback
is used only when ``SELFREPAIR_ENV`` is dev/test/local/ci or
``SELFREPAIR_INSECURE_COOKIES=1``.
"""
from __future__ import annotations

from .connector_service import decrypt, encrypt, ensure_encryption_configured, mask

__all__ = ["decrypt", "encrypt", "ensure_encryption_configured", "mask"]
