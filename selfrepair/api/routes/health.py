"""Health and readiness probes."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz", tags=["health"])
async def healthz() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/readyz", tags=["health"])
async def readyz() -> dict[str, str]:
    """Readiness probe. Real version pings Postgres + Redis; stub for now."""
    return {"status": "ready"}
