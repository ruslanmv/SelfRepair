"""PLANNING stage: match findings to fixers and run policy on each."""
from __future__ import annotations

import logging

from selfrepair.config.repo_config import RepoConfig
from selfrepair.fixers import default_registry
from selfrepair.persistence.repositories import ReposRepository
from selfrepair.policy import PolicyContext, default_engine
from selfrepair.policy.decisions import PolicyOutcome
from selfrepair.sdk import RepoContext
from selfrepair.state.machine import JobState
from selfrepair.worker.pipeline import StageContext, StageResult
from selfrepair.worker.stages.sandbox import workspace_for

logger = logging.getLogger(__name__)


async def plan_stage(ctx: StageContext) -> StageResult:
    findings = ctx.extra.get("scanned_findings", [])
    if not findings:
        return StageResult(
            next_state=JobState.COMPLETED,
            message="no findings; nothing to plan",
            payload={"plans": 0},
        )

    repos = ReposRepository(ctx.session)
    repo = await repos.get(ctx.repo_id)
    if repo is None:
        raise LookupError(f"repo {ctx.repo_id} not found")

    config: RepoConfig = ctx.extra.get("repo_config") or RepoConfig()
    workspace = workspace_for(ctx.job_id)
    repo_ctx = RepoContext(
        workspace=workspace,
        full_name=repo.full_name,
        default_branch=repo.default_branch,
        config=config.model_dump(),
    )

    registry = default_registry()
    engine = default_engine()
    plans: list[dict] = []
    skipped: list[dict] = []

    for finding in findings:
        candidates = list(registry.candidates_for(finding, repo_ctx))
        if not candidates:
            skipped.append({"finding": finding.kind, "reason": "no fixer"})
            continue
        fixer = candidates[0]
        plan = fixer.plan(finding, repo_ctx)
        decision = engine.evaluate(
            PolicyContext(
                finding=finding,
                plan=plan,
                repo_config=config,
                files_changed=plan.files_touched,
                is_llm_repair=False,
            )
        )
        if decision.outcome == PolicyOutcome.DENY:
            skipped.append(
                {
                    "finding": finding.kind,
                    "reason": f"policy:{decision.rule_id}",
                    "detail": decision.reason,
                }
            )
            continue
        plans.append(
            {
                "finding": finding,
                "plan": plan,
                "fixer_id": fixer.id,
                "policy_outcome": decision.outcome.value,
                "requires_approval": decision.requires_approval,
            }
        )

    ctx.extra["plans"] = plans
    if not plans:
        return StageResult(
            next_state=JobState.COMPLETED,
            message=f"no actionable plans (skipped={len(skipped)})",
            payload={"plans": 0, "skipped": skipped},
        )
    return StageResult(
        next_state=JobState.REPAIRING,
        message=f"{len(plans)} plan(s) ready",
        payload={"plans": len(plans), "skipped": len(skipped)},
    )
