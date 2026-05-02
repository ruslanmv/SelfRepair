"""CLONING stage: shallow-clone the target repo into the per-job workspace."""
from __future__ import annotations

import logging
import shutil
import subprocess

from selfrepair.persistence.repositories import ReposRepository
from selfrepair.state.machine import JobState
from selfrepair.worker.pipeline import StageContext, StageResult
from selfrepair.worker.stages.sandbox import workspace_for

logger = logging.getLogger(__name__)


async def clone_stage(ctx: StageContext) -> StageResult:
    repos = ReposRepository(ctx.session)
    repo = await repos.get(ctx.repo_id)
    if repo is None:
        raise LookupError(f"repo {ctx.repo_id} not found")

    workspace = workspace_for(ctx.job_id)
    if (workspace / ".git").is_dir():
        # Resume case: refresh.
        shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)

    clone_url = _clone_url_for(repo.provider, repo.full_name)
    cmd = [
        "git", "clone",
        "--depth=1",
        "--branch", repo.default_branch,
        clone_url,
        str(workspace),
    ]
    completed = subprocess.run(cmd, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "git clone failed: "
            + completed.stderr.decode("utf-8", errors="replace")
        )

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace, capture_output=True, check=True,
    ).stdout.decode().strip()
    ctx.extra["repo_sha"] = sha

    return StageResult(
        next_state=JobState.ANALYZING,
        message=f"cloned {repo.full_name}@{sha[:8]}",
        payload={"sha": sha, "branch": repo.default_branch},
    )


def _clone_url_for(provider: str, full_name: str) -> str:
    if provider == "github":
        return f"https://github.com/{full_name}.git"
    if provider == "gitlab":
        return f"https://gitlab.com/{full_name}.git"
    if provider == "huggingface":
        return f"https://huggingface.co/{full_name}"
    raise ValueError(f"unknown provider: {provider!r}")
