"""Dashboard metrics endpoint."""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.metrics.dashboard import compute_dashboard_metrics
from selfrepair.persistence import get_sessionmaker

router = APIRouter(prefix="/v1/metrics", tags=["metrics"])


async def _session() -> AsyncIterator[AsyncSession]:
    database_url = os.getenv(
        "SELFREPAIR_DATABASE_URL",
        "postgresql+asyncpg://selfrepair:selfrepair@localhost/selfrepair",
    )
    sessionmaker = get_sessionmaker(database_url)
    async with sessionmaker() as session:
        yield session


@router.get("/dashboard")
async def dashboard(
    session: AsyncSession = Depends(_session),
) -> dict[str, float | int | None]:
    metrics = await compute_dashboard_metrics(session)
    return {
        "auto_fix_success_rate": round(metrics.auto_fix_success_rate, 4),
        "mttr_seconds_avg": metrics.mttr_seconds_avg,
        "usd_per_repair_avg": round(metrics.usd_per_repair_avg, 4),
        "regression_rate": round(metrics.regression_rate, 4),
        "sample_size": metrics.sample_size,
    }
