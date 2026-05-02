"""Stable cross-provider fingerprints for external issues.

Used by the upsert path so re-syncing the same upstream issue doesn't
create duplicate rows when a provider rotates its internal id format.
The `(org_id, provider, provider_issue_id)` constraint already gives us
exact-match dedupe; the fingerprint is for the analytical layer ("is this
'CI fails on missing pyproject' issue the same one we saw on a different
provider?").

The fingerprint must be:
  - stable across re-syncs (title may shift slightly; we normalise)
  - deterministic (sha256 over a fixed input order, not dict iteration)
  - cross-provider (same logical issue on GH vs. mirror on GL → same fp)
"""
from __future__ import annotations

import hashlib
import re

# Strip a leading `[scope] ` tag, like `[BUG] ` or `[CI] `.
_TAG_PREFIX = re.compile(r"^\s*\[[^\]]+\]\s*")
# Collapse whitespace runs.
_WS = re.compile(r"\s+")
# Drop trailing parenthetical metadata like `(reopened)` or `(#1234)`.
_TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")


def normalize_title(title: str) -> str:
    """Reduce a title to its semantic shape.

    Lowercased, tag-prefix stripped, whitespace collapsed. Two re-titlings
    of the same issue ("[BUG] CI fails" → "CI fails when …") collapse to
    similar normal forms; the fingerprint stays stable.
    """
    s = title or ""
    s = _TAG_PREFIX.sub("", s)
    s = _TRAILING_PAREN.sub("", s)
    s = _WS.sub(" ", s).strip().lower()
    return s


def compute_fingerprint(
    *,
    repo_full_name: str,
    title: str,
    provider_issue_id: str,
) -> str:
    """SHA-256 over `repo|title|provider_issue_id`, truncated to 32 hex chars.

    `provider_issue_id` is included so the same title under two different
    repos doesn't collide; `repo_full_name` is included so the same title
    on two providers (mirror) shares the prefix when the repo names match.
    """
    parts = [
        (repo_full_name or "").strip().lower(),
        normalize_title(title),
        (provider_issue_id or "").strip(),
    ]
    material = "\x00".join(parts).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:32]
