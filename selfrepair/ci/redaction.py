"""Redact secrets from CI logs before persisting or sending to an LLM.

Two non-obvious rules from the design:

1. Redact to a stable token (`<<REDACTED:type:hash6>>`), not `***`.
   Same secret in same place produces the same token — fingerprints stay
   stable across runs while the secret never leaves the regex.
2. Redact before excerpting. Redaction is the entry gate; nothing else
   touches the raw log first.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass

# Patterns are ordered by specificity. Cloud creds first so they don't get
# clipped by the generic key=value rule.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "aws_secret",
        re.compile(
            r"(?i)aws[_-]?secret[_-]?access[_-]?key[\"'\s:=]+([A-Za-z0-9/+=]{40})"
        ),
    ),
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+PRIVATE KEY-----"
        ),
    ),
    ("github_pat", re.compile(r"github_pat_[A-Za-z0-9_]{82,}")),
    ("github_classic", re.compile(r"ghp_[A-Za-z0-9]{36,}")),
    ("github_server", re.compile(r"ghs_[A-Za-z0-9]{36,}")),
    ("github_oauth", re.compile(r"gho_[A-Za-z0-9]{36,}")),
    ("github_user", re.compile(r"ghu_[A-Za-z0-9]{36,}")),
    ("github_refresh", re.compile(r"ghr_[A-Za-z0-9]{36,}")),
    ("gitlab_pat", re.compile(r"glpat-[A-Za-z0-9_\-]{20,}")),
    ("hf_token", re.compile(r"hf_[A-Za-z0-9]{34,}")),
    ("openai_or_claude", re.compile(r"sk-(?:ant-)?[A-Za-z0-9_\-]{32,}")),
    ("npm_token", re.compile(r"npm_[A-Za-z0-9]{36,}")),
    ("pypi_token", re.compile(r"pypi-AgENdGV[A-Za-z0-9_\-]{40,}")),
    (
        "auth_header",
        re.compile(r"(?i)(authorization|x-api-key|x-auth-token):\s*\S+"),
    ),
    (
        "kv_secret",
        re.compile(
            r"(?i)(password|secret|token|api[_-]?key)[\"'\s:=]+([^\s\"']{8,})"
        ),
    ),
    # URL-embedded creds: scheme://user:pass@host
    (
        "url_cred",
        re.compile(r"\b[a-z][a-z0-9+\-.]*://[^\s/@]+:[^\s/@]+@[^\s/]+"),
    ),
]

# Last-resort entropy pass: only kicks in for tokens that didn't match any
# specific pattern. Tokens shorter than this aren't entropy-screened
# (false-positive rate climbs sharply on prose).
_ENTROPY_MIN_LEN = 24
_ENTROPY_THRESHOLD = 4.0  # Shannon bits/char; ~4.0 catches base64/hex blobs.
_TOKEN_RE = re.compile(r"[A-Za-z0-9+/=_\-]{24,}")


@dataclass(frozen=True)
class RedactionResult:
    text: str
    secrets_found: int
    classes_seen: tuple[str, ...]


def redact(text: str) -> RedactionResult:
    """Redact secrets in `text`, returning the rewritten text and a count.

    Each match becomes `<<REDACTED:type:hash6>>` where `hash6` is the
    first 6 chars of sha256(raw secret). Same secret → same token, so
    fingerprints stay stable across runs.
    """
    if not text:
        return RedactionResult(text=text, secrets_found=0, classes_seen=())

    out = text
    counter: Counter[str] = Counter()

    for kind, pattern in _PATTERNS:
        def _sub(match: re.Match[str], _kind: str = kind) -> str:
            counter[_kind] += 1
            return _token(_kind, match.group(0))

        out = pattern.sub(_sub, out)

    # Entropy pass on remaining tokens (skips already-redacted markers).
    out = _TOKEN_RE.sub(
        lambda m: _maybe_redact_high_entropy(m.group(0), counter), out
    )

    return RedactionResult(
        text=out,
        secrets_found=sum(counter.values()),
        classes_seen=tuple(sorted(counter)),
    )


def _maybe_redact_high_entropy(token: str, counter: Counter[str]) -> str:
    if token.startswith("<<REDACTED:"):
        return token
    if len(token) < _ENTROPY_MIN_LEN:
        return token
    if _shannon_entropy(token) < _ENTROPY_THRESHOLD:
        return token
    counter["high_entropy"] += 1
    return _token("high_entropy", token)


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    counts = Counter(s).values()
    return -sum((c / n) * math.log2(c / n) for c in counts)


def _token(kind: str, raw: str) -> str:
    digest = hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:6]
    return f"<<REDACTED:{kind}:{digest}>>"
