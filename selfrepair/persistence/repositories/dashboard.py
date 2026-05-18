"""Aggregations for the operator console's overview surface.

One method, `compute(org_id)`, runs every query the dashboard needs in
a predictable order. It returns a plain dict so the route layer doesn't
have to know about ORM types and so the SPA's response stays
schema-stable across refactors.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.metrics.dashboard import compute_dashboard_metrics_for_org
from selfrepair.persistence.models import (
    Finding,
    FindingStatus,
    Job,
    JobEvent,
    Repair,
    RepairState,
    Repo,
)

# Health-band thresholds mirror the simple finding-count heuristic the
# repos read API uses. Replace with severity-weighted scoring once the
# scorer lands; the band labels stay stable for the SPA.
_BANDS = (
    ("90-100", 0, 2),     # 0..2 open findings  -> score 90..100
    ("70-89", 3, 6),      # 3..6                -> score 70..85
    ("50-69", 7, 10),     # 7..10               -> score 50..65
    ("<50", 11, 10**6),   # 11+                 -> below 50
)


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def compute(self, org_id: uuid.UUID) -> dict[str, Any]:
        kpis = await self._kpis(org_id)
        fleet_health = await self._fleet_health(org_id)
        repair_cost = await self._repair_cost(org_id)
        activity = await self._activity(org_id)
        awaiting_approval = await self._awaiting_approval(org_id)
        return {
            "kpis": kpis,
            "fleet_health": fleet_health,
            "repair_cost": repair_cost,
            "activity": activity,
            "awaiting_approval": awaiting_approval,
        }

    # ---------------------------- KPIs ----------------------------

    async def _kpis(self, org_id: uuid.UUID) -> dict[str, Any]:
        repos_total = (
            await self._session.execute(
                select(func.count(Repo.id)).where(
                    Repo.org_id == org_id, Repo.archived_at.is_(None)
                )
            )
        ).scalar_one()

        open_findings = (
            await self._session.execute(
                select(func.count(Finding.id)).where(
                    Finding.org_id == org_id,
                    Finding.status == FindingStatus.OPEN,
                )
            )
        ).scalar_one()

        metrics = await compute_dashboard_metrics_for_org(
            self._session, org_id
        )

        # Monthly spend = sum(cost_usd) for repairs created since the
        # first of the current UTC month.
        first_of_month = datetime.now(UTC).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        monthly_spend = (
            await self._session.execute(
                select(func.coalesce(func.sum(Repair.cost_usd), 0))
                .select_from(Repair)
                .join(Job, Job.id == Repair.job_id)
                .where(
                    Job.org_id == org_id,
                    Repair.created_at >= first_of_month,
                )
            )
        ).scalar_one()

        return {
            "repos_total": int(repos_total),
            "open_findings": int(open_findings),
            "auto_fix_success_rate": round(
                metrics.auto_fix_success_rate, 4
            ),
            "mttr_seconds_avg": metrics.mttr_seconds_avg,
            "usd_per_repair_avg": round(metrics.usd_per_repair_avg, 4),
            "regression_rate": round(metrics.regression_rate, 4),
            "sample_size": metrics.sample_size,
            "monthly_spend_usd": float(monthly_spend),
        }

    # ------------------------- fleet health ------------------------

    async def _fleet_health(self, org_id: uuid.UUID) -> list[dict[str, Any]]:
        of_sq = (
            select(
                Finding.repo_id.label("repo_id"),
                func.count(Finding.id).label("cnt"),
            )
            .where(
                Finding.org_id == org_id,
                Finding.status == FindingStatus.OPEN,
            )
            .group_by(Finding.repo_id)
            .subquery()
        )
        per_repo = (
            select(
                Repo.id.label("repo_id"),
                func.coalesce(of_sq.c.cnt, 0).label("cnt"),
            )
            .outerjoin(of_sq, of_sq.c.repo_id == Repo.id)
            .where(Repo.org_id == org_id, Repo.archived_at.is_(None))
            .subquery()
        )
        cols = []
        for label, lo, hi in _BANDS:
            cols.append(
                func.sum(
                    case(
                        (
                            (per_repo.c.cnt >= lo) & (per_repo.c.cnt <= hi),
                            1,
                        ),
                        else_=0,
                    )
                ).label(label.replace("-", "_").replace("<", "lt"))
            )
        row = (
            await self._session.execute(select(*cols).select_from(per_repo))
        ).first()
        if row is None:
            return [{"band": b[0], "count": 0} for b in _BANDS]
        return [
            {"band": label, "count": int(row[i] or 0)}
            for i, (label, _lo, _hi) in enumerate(_BANDS)
        ]

    # ------------------------- repair cost ------------------------

    async def _repair_cost(self, org_id: uuid.UUID) -> dict[str, Any]:
        first_of_month = datetime.now(UTC).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        spend = (
            await self._session.execute(
                select(func.coalesce(func.sum(Repair.cost_usd), 0))
                .select_from(Repair)
                .join(Job, Job.id == Repair.job_id)
                .where(
                    Job.org_id == org_id,
                    Repair.created_at >= first_of_month,
                )
            )
        ).scalar_one()
        month_label = first_of_month.strftime("%B %Y")
        return {
            "spend_usd": float(spend or 0),
            "month": first_of_month.date().isoformat(),
            "month_label": month_label,
        }

    # ---------------------------- activity ------------------------

    async def _activity(self, org_id: uuid.UUID) -> list[dict[str, Any]]:
        """Latest job_event rows joined to their repo for context.

        Capped at 20; the SPA paginates on demand once it ships an
        "all activity" surface.
        """
        stmt = (
            select(JobEvent, Job, Repo)
            .join(Job, Job.id == JobEvent.job_id)
            .join(Repo, Repo.id == Job.repo_id)
            .where(Job.org_id == org_id)
            .order_by(JobEvent.ts.desc())
            .limit(20)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "event_id": e.id,
                "job_id": str(j.id),
                "repo_id": str(r.id),
                "repo_full_name": r.full_name,
                "ts": e.ts.isoformat(),
                "stage": (
                    e.stage.value if hasattr(e.stage, "value") else e.stage
                ),
                "level": e.level,
                "message": e.message,
            }
            for (e, j, r) in rows
        ]

    # ------------------------ awaiting approval -------------------

    async def _awaiting_approval(
        self, org_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Repairs in `published` state — PR open, awaiting human review.

        Once the policy engine writes `requires_approval=true` rows on
        every repair this can tighten to the explicit
        "requires_approval AND not yet decided" definition, but
        published-but-not-merged is the right user-visible bucket today.
        """
        stmt = (
            select(Repair, Repo, Finding)
            .join(Job, Job.id == Repair.job_id)
            .join(Repo, Repo.id == Job.repo_id)
            .join(Finding, Finding.id == Repair.finding_id)
            .where(
                Job.org_id == org_id,
                Repair.state == RepairState.PUBLISHED,
            )
            .order_by(Repair.created_at.desc())
            .limit(20)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "repair_id": str(rep.id),
                "created_at": rep.created_at.isoformat(),
                "pr_url": rep.pr_url,
                "cost_usd": float(rep.cost_usd or 0),
                "fixer_id": rep.fixer_id,
                "repo": {
                    "id": str(repo.id),
                    "provider": repo.provider,
                    "full_name": repo.full_name,
                },
                "finding": {
                    "id": str(f.id),
                    "kind": f.kind,
                    "severity": f.severity,
                },
            }
            for (rep, repo, f) in rows
        ]
