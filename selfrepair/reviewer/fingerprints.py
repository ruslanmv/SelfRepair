"""Stable finding fingerprints.

The same rule, path, and normalized evidence hashes to the same value across
runs, so a republish can update a comment instead of adding a second one.
The hash does not include the secret text: callers redact evidence first.
"""
from __future__ import annotations

import hashlib
import re

_WS = re.compile(r"\s+")


def fingerprint(
    *,
    category: str,
    file_path: str | None,
    title: str,
    evidence: str | None,
) -> str:
    """Return a 64-char hex fingerprint for one finding."""
    normalized = _WS.sub(" ", (evidence or title).strip().lower())[:500]
    payload = "\n".join(
        [
            category.strip().lower(),
            (file_path or "").strip(),
            title.strip().lower(),
            normalized,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
