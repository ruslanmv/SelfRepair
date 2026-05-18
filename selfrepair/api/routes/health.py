"""Health and readiness probes.

`/healthz` is a process-liveness check (the API responded). `/readyz`
asserts that downstream dependencies the API actually requires —
Postgres and Redis — are reachable. A failed readiness check returns
503 so Kubernetes/Compose can take the pod out of rotation rather than
routing traffic into a half-broken stack.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

from selfrepair.api.deps import get_app_sessionmaker

logger = logging.getLogger(__name__)
router = APIRouter()

_PROBE_TIMEOUT_SECONDS = 2.0


@router.get("/healthz", tags=["health"])
async def healthz() -> dict[str, str]:
    """Liveness probe — cheap, never touches dependencies."""
    return {"status": "ok"}


async def _check_postgres() -> tuple[bool, str | None]:
    try:
        sessionmaker = get_app_sessionmaker()
        async with sessionmaker() as session:
            await asyncio.wait_for(
                session.execute(text("SELECT 1")),
                timeout=_PROBE_TIMEOUT_SECONDS,
            )
        return True, None
    except Exception as exc:  # pragma: no cover - error path is the value
        logger.warning("readyz: postgres check failed", exc_info=True)
        return False, str(exc)


async def _check_redis(request: Request) -> tuple[bool, str | None]:
    queue = getattr(request.app.state, "queue", None)
    if queue is None:
        return False, "redis pool unavailable"
    try:
        result = await asyncio.wait_for(
            queue.ping(), timeout=_PROBE_TIMEOUT_SECONDS
        )
        return bool(result), None
    except Exception as exc:  # pragma: no cover
        logger.warning("readyz: redis check failed", exc_info=True)
        return False, str(exc)


@router.get("/readyz", tags=["health"])
async def readyz(request: Request, response: Response) -> dict[str, Any]:
    """Readiness probe.

    Pings Postgres (`SELECT 1`) and Redis (`PING`). Returns 503 if either
    is down; the body always carries per-component status so the operator
    console can render a clean degraded banner.
    """
    pg_ok, pg_err = await _check_postgres()
    redis_ok, redis_err = await _check_redis(request)
    overall = pg_ok and redis_ok
    if not overall:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if overall else "degraded",
        "checks": {
            "postgres": {"ok": pg_ok, "error": pg_err},
            "redis": {"ok": redis_ok, "error": redis_err},
        },
    }
