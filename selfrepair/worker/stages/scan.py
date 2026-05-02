"""SCANNING stage: run all bundled scanners and persist findings."""
from __future__ import annotations

import logging

from selfrepair.persistence.repositories import FindingsRepository
from selfrepair.scanners import discover_scanners, run_scanner
from selfrepair.state.machine import JobState
from selfrepair.worker.pipeline import StageContext, StageResult
from selfrepair.worker.stages.sandbox import workspace_for

logger = logging.getLogger(__name__)


async def scan_stage(ctx: StageContext) -> StageResult:
    workspace = workspace_for(ctx.job_id)
    sha = ctx.extra.get("repo_sha")
    findings_repo = FindingsRepository(ctx.session)

    plugins = discover_scanners()
    if not plugins:
        return StageResult(
            next_state=JobState.PLANNING,
            message="no scanners configured",
            payload={"scanners": 0, "findings": 0},
        )

    total = 0
    per_scanner: dict[str, int] = {}
    findings_for_planner: list = []
    for plugin in plugins:
        try:
            run = run_scanner(plugin, workspace=workspace)
        except Exception:
            logger.exception("scanner %s failed", plugin.id)
            per_scanner[plugin.id] = -1
            continue
        per_scanner[plugin.id] = len(run.sarif_result.findings)
        total += len(run.sarif_result.findings)
        for finding in run.sarif_result.findings:
            await findings_repo.upsert_by_fingerprint(
                org_id=ctx.org_id,
                repo_id=ctx.repo_id,
                sha=sha,
                finding=finding,
            )
            findings_for_planner.append(finding)

    ctx.extra["scanned_findings"] = findings_for_planner
    return StageResult(
        next_state=JobState.PLANNING,
        message=f"{total} findings across {len(plugins)} scanner(s)",
        payload={"scanners": per_scanner, "findings": total},
    )
