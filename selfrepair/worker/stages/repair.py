"""REPAIRING stage: run each plan's fixer and apply the diff to the workspace."""
from __future__ import annotations

import logging
import subprocess

from selfrepair.fixers import default_registry
from selfrepair.persistence.models import RepairMode
from selfrepair.persistence.repositories import (
    FindingsRepository,
    RepairsRepository,
)
from selfrepair.sdk import RepoContext
from selfrepair.state.machine import JobState
from selfrepair.worker.pipeline import StageContext, StageResult
from selfrepair.worker.stages.sandbox import workspace_for

logger = logging.getLogger(__name__)


async def repair_stage(ctx: StageContext) -> StageResult:
    plans = ctx.extra.get("plans", [])
    if not plans:
        return StageResult(
            next_state=JobState.COMPLETED,
            message="no plans to apply",
            payload={"applied": 0},
        )

    workspace = workspace_for(ctx.job_id)
    repo_ctx = RepoContext(
        workspace=workspace,
        full_name=str(ctx.repo_id),
        default_branch="main",
    )

    findings_repo = FindingsRepository(ctx.session)
    repairs_repo = RepairsRepository(ctx.session)
    registry = default_registry()

    applied: list[dict] = []
    for plan_record in plans:
        finding = plan_record["finding"]
        plan = plan_record["plan"]
        fixer_id = plan_record["fixer_id"]
        candidates = [
            f for f in registry.candidates_for(finding, repo_ctx)
            if f.id == fixer_id
        ]
        if not candidates:
            continue
        fixer = candidates[0]

        patch = fixer.apply(plan, repo_ctx)
        if not patch.diff:
            continue

        finding_row = await findings_repo.upsert_by_fingerprint(
            org_id=ctx.org_id,
            repo_id=ctx.repo_id,
            sha=ctx.extra.get("repo_sha"),
            finding=finding,
        )
        repair = await repairs_repo.create(
            finding_id=finding_row.id,
            job_id=ctx.job_id,
            fixer_id=fixer_id,
            mode=RepairMode.DETERMINISTIC,
        )

        completed = subprocess.run(
            ["git", "apply", "-"],
            input=patch.diff.encode("utf-8"),
            cwd=workspace,
            capture_output=True,
        )
        if completed.returncode != 0:
            logger.warning(
                "git apply failed for repair %s: %s",
                repair.id,
                completed.stderr.decode("utf-8", errors="replace"),
            )
            continue
        applied.append(
            {
                "repair_id": str(repair.id),
                "fixer_id": fixer_id,
                "finding_kind": finding.kind,
                "files_changed": list(patch.files_changed),
                "plan": plan,
                "finding": finding,
                "patch": patch,
            }
        )

    ctx.extra["applied_repairs"] = applied
    return StageResult(
        next_state=JobState.VALIDATING,
        message=f"{len(applied)} patch(es) applied",
        payload={"applied": len(applied)},
    )
