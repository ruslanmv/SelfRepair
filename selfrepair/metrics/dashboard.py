"""Compute the four product metrics from the repair table."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.models import Finding, Repair, RepairState


@dataclass(frozen=True)
class DashboardMetrics:
    auto_fix_success_rate: float       # 0..1
    mttr_seconds_avg: float | None     # null until at least one merge
    usd_per_repair_avg: float          # over published+merged repairs
    regression_rate: float             # reverted / (merged + reverted)
    sample_size: int                   # how many merged+failed+reverted contribute


async def compute_dashboard_metrics(
    session: AsyncSession,
) -> DashboardMetrics:
    merged = await _count(session, Repair.state == RepairState.MERGED)
    failed = await _count(
        session,
        Repair.state.in_([RepairState.FAILED, RepairState.REVERTED]),
    )
    reverted = await _count(session, Repair.state == RepairState.REVERTED)

    total_outcome = merged + failed
    success_rate = (merged / total_outcome) if total_outcome else 0.0

    mttr_stmt = (
        select(
            func.avg(
                func.extract("epoch", Repair.created_at)
                - func.extract("epoch", Finding.first_seen_at)
            )
        )
        .select_from(Repair)
        .join(Finding, Finding.id == Repair.finding_id)
        .where(Repair.state == RepairState.MERGED)
    )
    mttr = (await session.execute(mttr_stmt)).scalar()

    usd_stmt = select(func.avg(Repair.cost_usd)).where(
        Repair.state.in_([RepairState.PUBLISHED, RepairState.MERGED])
    )
    avg_cost = (await session.execute(usd_stmt)).scalar() or 0.0

    regression_total = merged + reverted
    regression_rate = (
        (reverted / regression_total) if regression_total else 0.0
    )

    return DashboardMetrics(
        auto_fix_success_rate=success_rate,
        mttr_seconds_avg=float(mttr) if mttr is not None else None,
        usd_per_repair_avg=float(avg_cost),
        regression_rate=regression_rate,
        sample_size=total_outcome,
    )


async def _count(session: AsyncSession, *predicates) -> int:
    stmt = select(func.count(Repair.id)).where(*predicates)
    result = await session.execute(stmt)
    return int(result.scalar() or 0)
