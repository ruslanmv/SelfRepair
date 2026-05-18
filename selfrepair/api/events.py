"""Per-job event pub/sub for the SSE live stream.

The worker publishes one JSON message per `job_event` row to a Redis
channel keyed by `job_id`. SSE subscribers in the API hold one
long-lived response per client, replay any rows the client missed (via
`Last-Event-ID`), then forward live messages until the client
disconnects.

Channel naming keeps the job ID in the suffix so each connection serves
exactly one job and there is no cross-tenant fan-out at the broker.
A module-level singleton client is used on the worker side so the
pipeline doesn't open/close a Redis connection on every transition.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

try:  # pragma: no cover - import guard for environments without redis
    from redis.asyncio import Redis
except Exception:  # pragma: no cover
    Redis = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "selfrepair:job_events"
KEEPALIVE_SECONDS = 15.0


def channel_for(job_id: uuid.UUID | str) -> str:
    return f"{CHANNEL_PREFIX}:{job_id}"


def get_redis_url() -> str:
    return os.getenv("SELFREPAIR_REDIS_URL", "redis://localhost:6379/0")


def make_redis_client() -> Any:
    if Redis is None:  # pragma: no cover
        raise RuntimeError("redis package not installed")
    return Redis.from_url(get_redis_url(), decode_responses=True)


async def aclose(client: Any) -> None:
    """Close a redis client across redis-py 4.x and 5.x."""
    if client is None:
        return
    try:
        if hasattr(client, "aclose"):
            await client.aclose()
        else:  # redis-py < 5
            await client.close()
    except Exception:  # pragma: no cover - best effort
        logger.debug("error closing redis client", exc_info=True)


# ----------------------------- producer -----------------------------------


_producer_lock = asyncio.Lock()
_producer: Any = None


async def _get_producer() -> Any | None:
    """Module-level publisher reused by the worker.

    The worker calls `publish_job_event` after every state transition;
    opening a new Redis connection per transition would be wasteful.
    Returns None if the redis package is not importable so callers can
    skip publish silently.
    """
    global _producer
    if Redis is None:
        return None
    if _producer is not None:
        return _producer
    async with _producer_lock:
        if _producer is None:
            try:
                _producer = make_redis_client()
            except Exception:  # pragma: no cover - non-fatal
                logger.warning(
                    "could not initialise redis publisher; SSE will be silent",
                    exc_info=True,
                )
                _producer = None
    return _producer


async def publish_job_event(
    job_id: uuid.UUID, payload: dict[str, Any]
) -> int:
    """Best-effort publish to the job's channel.

    Never raises: SSE is a UX nicety, not a correctness gate. A pub/sub
    failure must not break the worker pipeline.
    """
    producer = await _get_producer()
    if producer is None:
        return 0
    try:
        return int(
            await producer.publish(
                channel_for(job_id),
                json.dumps(payload, default=str),
            )
        )
    except Exception:
        logger.warning("publish_job_event failed", exc_info=True)
        return 0


# ----------------------------- consumer -----------------------------------


@asynccontextmanager
async def subscribe(job_id: uuid.UUID) -> AsyncIterator[Any]:
    """Subscribe to one job's channel.

    Each SSE response opens its own client + pubsub so a slow consumer
    can't backpressure other connections sharing a singleton.
    """
    if Redis is None:  # pragma: no cover
        raise RuntimeError("redis package not installed")
    client = make_redis_client()
    pubsub = client.pubsub()
    await pubsub.subscribe(channel_for(job_id))
    try:
        yield pubsub
    finally:
        try:
            await pubsub.unsubscribe(channel_for(job_id))
        except Exception:
            pass
        try:
            await pubsub.close()
        except Exception:
            pass
        await aclose(client)
