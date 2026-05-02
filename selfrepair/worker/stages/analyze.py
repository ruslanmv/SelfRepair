"""ANALYZING stage: load `.selfrepair.yml` from the workspace."""
from __future__ import annotations

from selfrepair.config.repo_config import load_repo_config
from selfrepair.state.machine import JobState
from selfrepair.worker.pipeline import StageContext, StageResult
from selfrepair.worker.stages.sandbox import workspace_for


async def analyze_stage(ctx: StageContext) -> StageResult:
    workspace = workspace_for(ctx.job_id)
    config = load_repo_config(workspace)
    ctx.extra["repo_config"] = config
    return StageResult(
        next_state=JobState.SCANNING,
        message="repo config loaded",
        payload={
            "schedule": config.schedule,
            "llm_kinds_enabled": [r.kind for r in config.escalate_to_llm],
            "auto_merge_kinds": [r.kind for r in config.auto_merge],
            "codeowners_required": config.codeowners_required,
        },
    )
