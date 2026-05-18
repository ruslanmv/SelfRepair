"""Compute the four product metrics from the repair table.

Two entry points are exposed:

* `compute_dashboard_metrics` — fleet-wide; kept for the legacy
  `/v1/metrics/dashboard` route and any internal tooling that doesn't
  care about tenancy.
* `compute_dashboard_metrics_for_org` — org-scoped; used by the new
  `/v1/dashboard` aggregate. Repair has no `org_id` of its own, so
  scoping joins through `job` (Repair -> Job -> org_id) and through
  `finding` for the MTTR computation.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.models import Finding, Job, Repair, RepairState


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
    """Fleet-wide variant. Kept for backwards compatibility."""
    return await _compute(session, org_id=None)


async def compute_dashboard_metrics_for_org(
    session: AsyncSession, org_id: uuid.UUID,
) -> DashboardMetrics:
    """Org-scoped variant used by the SPA dashboard."""
    return await _compute(session, org_id=org_id)


def _maybe_org_filter(stmt: Any, org_id: uuid.UUID | None) -> Any:
    if org_id is None:
        return stmt
    return stmt.where(Job.org_id == org_id)


async def _compute(
    session: AsyncSession, *, org_id: uuid.UUID | None
) -> DashboardMetrics:
    merged = await _count(session, RepairState.MERGED, org_id)
    failed_or_reverted = await _count_in(
        session,
        [RepairState.FAILED, RepairState.REVERTED],
        org_id,
    )
    reverted = await _count(session, RepairState.REVERTED, org_id)

    total_outcome = merged + failed_or_reverted
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
        .join(Job, Job.id == Repair.job_id)
        .where(Repair.state == RepairState.MERGED)
    )
    mttr_stmt = _maybe_org_filter(mttr_stmt, org_id)
    mttr = (await session.execute(mttr_stmt)).scalar()

    usd_stmt = (
        select(func.avg(Repair.cost_usd))
        .select_from(Repair)
        .join(Job, Job.id == Repair.job_id)
        .where(
            Repair.state.in_([RepairState.PUBLISHED, RepairState.MERGED])
        )
    )
    usd_stmt = _maybe_org_filter(usd_stmt, org_id)
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


async def _count(
    session: AsyncSession,
    state: RepairState,
    org_id: uuid.UUID | None,
) -> int:
    return await _count_in(session, [state], org_id)


async def _count_in(
    session: AsyncSession,
    states: list[RepairState],
    org_id: uuid.UUID | None,
) -> int:
    stmt = (
        select(func.count(Repair.id))
        .select_from(Repair)
        .join(Job, Job.id == Repair.job_id)
        .where(Repair.state.in_(states))
    )
    stmt = _maybe_org_filter(stmt, org_id)
    result = await session.execute(stmt)
    return int(result.scalar() or 0)
