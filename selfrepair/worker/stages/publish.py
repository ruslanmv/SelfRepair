"""PUBLISHING stage: run the publisher (gitleaks gate → commit → push → PR).

Multi-PR per job is a future iteration: today we publish the first applied
repair only so CODEOWNERS spam (design §10) stays bounded. Batched-by-
reviewer publishing lands when the inventory grows large enough to need it.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from selfrepair.git import GitleaksTripped, publish_repair
from selfrepair.state.machine import JobState
from selfrepair.worker.pipeline import StageContext, StageResult
from selfrepair.worker.stages.sandbox import workspace_for

logger = logging.getLogger(__name__)


async def publish_stage(ctx: StageContext) -> StageResult:
    applied = ctx.extra.get("applied_repairs", [])
    if not applied:
        return StageResult(
            next_state=JobState.COMPLETED,
            message="nothing to publish",
        )

    record = applied[0]
    workspace = workspace_for(ctx.job_id)
    plan = record["plan"]
    finding = record["finding"]
    patch = record["patch"]

    branch = (
        f"selfrepair/{finding.kind}/"
        f"{datetime.now(UTC):%Y%m%d-%H%M%S}"
    )
    try:
        result = publish_repair(
            workspace=workspace,
            patch=patch,
            plan=plan,
            finding=finding,
            branch_name=branch,
            base_branch="main",
            rationale=plan.summary,
            open_pr=True,
        )
    except GitleaksTripped as exc:
        logger.error("gitleaks tripped: %s", exc)
        return StageResult(
            next_state=JobState.ESCALATED,
            message=f"gitleaks tripped: {exc}",
        )

    return StageResult(
        next_state=JobState.AWAITING_REVIEW,
        message=f"PR opened: {result.pr_url}",
        payload={
            "branch": result.branch,
            "commit_sha": result.commit_sha,
            "pr_url": result.pr_url,
            "reviewers": list(result.requested_reviewers),
            "signed": result.signature is not None,
        },
    )
