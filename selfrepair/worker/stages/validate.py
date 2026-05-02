"""VALIDATING stage: run the repaired workspace's tests.

For the foundation this is `make test` with a timeout. Full sandbox
integration (gVisor / Firecracker per design §2) is a later batch; until
then the worker container itself is the sandbox boundary.
"""
from __future__ import annotations

import logging
import subprocess

from selfrepair.state.machine import JobState
from selfrepair.worker.pipeline import StageContext, StageResult
from selfrepair.worker.stages.sandbox import workspace_for

logger = logging.getLogger(__name__)


async def validate_stage(ctx: StageContext) -> StageResult:
    workspace = workspace_for(ctx.job_id)
    if not (workspace / "Makefile").is_file():
        return StageResult(
            next_state=JobState.PUBLISHING,
            message="no Makefile; skipping validation",
            payload={"validated": True, "test_run": False},
        )
    completed = subprocess.run(
        ["make", "test"],
        cwd=workspace,
        capture_output=True,
        timeout=600,
    )
    if completed.returncode == 0:
        return StageResult(
            next_state=JobState.PUBLISHING,
            message="tests passed",
            payload={"validated": True, "test_run": True},
        )
    return StageResult(
        next_state=JobState.FAILED_VALIDATION,
        message="tests failed",
        payload={
            "validated": False,
            "test_run": True,
            "stdout_tail": completed.stdout.decode("utf-8", errors="replace")[-2000:],
            "stderr_tail": completed.stderr.decode("utf-8", errors="replace")[-2000:],
        },
    )
