"""Redis-backed ephemeral storage for the SelfRepair auth flows.

Uses Upstash Redis over its REST API for:
  - one-time email-verification and password-reset tokens (TTL'd), and
  - fixed-window rate limiting on auth endpoints.

If Upstash is not configured (or unreachable), it transparently falls back to
an in-process TTL dict so the app still works in local/dev runs. Rate limiting
fails open on backend errors to preserve availability.
"""
from __future__ import annotations

import logging
import os
import secrets
import time

logger = logging.getLogger(__name__)

_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

_client = None
_mem: dict[str, tuple[str, float]] = {}  # key -> (value, expires_at)


def _get_client():
    global _client
    if _client is not None:
        return _client
    if _URL and _TOKEN:
        try:
            from upstash_redis import Redis

            _client = Redis(url=_URL, token=_TOKEN)
            return _client
        except Exception as exc:  # pragma: no cover
            logger.warning("Upstash Redis unavailable (%s); using in-memory store.", exc)
    return None


def _mem_get(key: str) -> str | None:
    item = _mem.get(key)
    if not item:
        return None
    value, exp = item
    if exp and exp < time.time():
        _mem.pop(key, None)
        return None
    return value


def configured() -> bool:
    return bool(_URL and _TOKEN)


# --------------------------------------------------------------------------
# One-time tokens
# --------------------------------------------------------------------------

def put_token(kind: str, value: str, ttl_seconds: int) -> str:
    """Store ``value`` under a fresh opaque token; return the token."""
    token = secrets.token_urlsafe(32)
    key = f"sr:tok:{kind}:{token}"
    client = _get_client()
    if client is not None:
        try:
            client.set(key, value, ex=ttl_seconds)
            return token
        except Exception as exc:  # pragma: no cover
            logger.warning("Redis set failed (%s); using memory.", exc)
    _mem[key] = (value, time.time() + ttl_seconds)
    return token


def pop_token(kind: str, token: str) -> str | None:
    """Atomically read and consume a one-time token."""
    if not token:
        return None
    key = f"sr:tok:{kind}:{token}"
    client = _get_client()
    if client is not None:
        try:
            value = client.get(key)
            if value is not None:
                client.delete(key)
            return value
        except Exception as exc:  # pragma: no cover
            logger.warning("Redis get failed (%s); using memory.", exc)
    value = _mem_get(key)
    if value is not None:
        _mem.pop(key, None)
    return value


# --------------------------------------------------------------------------
# Rate limiting (fixed window)
# --------------------------------------------------------------------------

def rate_limit(action: str, identifier: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Return (allowed, remaining). Fails open on backend errors."""
    key = f"sr:rl:{action}:{identifier}"
    client = _get_client()
    if client is not None:
        try:
            count = client.incr(key)
            if count == 1:
                client.expire(key, window_seconds)
            remaining = max(0, limit - count)
            return count <= limit, remaining
        except Exception as exc:  # pragma: no cover
            logger.warning("Redis rate_limit failed (%s); allowing.", exc)
            return True, limit
    # in-memory window
    now = time.time()
    bucket = _mem_get(key)
    count = int(bucket) + 1 if bucket else 1
    if count == 1:
        _mem[key] = ("1", now + window_seconds)
    else:
        _, exp = _mem[key]
        _mem[key] = (str(count), exp)
    return count <= limit, max(0, limit - count)
