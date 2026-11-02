"""Turn an accepted review finding into a GitPilot repair plan.

The plan matches the live GitPilot `POST /repair` contract
(`gitpilot.repair.schema.RepairRequest`): dry-run unless a human approved a
draft, allowed paths limited to the finding's file, and no auto-merge.
Fork pull requests are refused. The review engine is not given this client.
"""
from __future__ import annotations

import uuid
from typing import Any

from selfrepair.config.repo_config import ReviewerConfig
from selfrepair.reviewer.schemas import FindingRecord, RunRecord

_FORBIDDEN = [".env", "secrets/**", "**/*token*", "**/*secret*", "migrations/**", "infra/prod/**"]


class RemediationRefused(Exception):
    """The finding cannot become a coding task."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def build_repair_plan(
    *,
    run: RunRecord,
    finding: FindingRecord,
    repo_url: str,
    config: ReviewerConfig,
    human_approved: bool,
    base_branch: str = "main",
) -> dict[str, Any]:
    """Build a repair-plan JSON body for `POST /repair`.

    `mode` is `dry_run` until remediation is enabled and a human approved the
    task. `draft_pr` is the strongest mode this function emits. It never sets
    a merge flag.
    """
    if not config.remediation.enabled:
        raise RemediationRefused("remediation disabled")
    if run.from_fork:
        raise RemediationRefused("fork pull requests are not remediated")
    if finding.validation_state != "accepted":
        raise RemediationRefused("finding was not accepted")
    if not finding.file_path or ".." in finding.file_path.split("/"):
        raise RemediationRefused("finding path is not a repository path")
    if config.remediation.require_human_approval and not human_approved:
        mode = "dry_run"
    elif human_approved:
        mode = "draft_pr"
    else:
        mode = "dry_run"
    severity = finding.severity if finding.severity in {"low", "medium", "high", "critical"} else "medium"
    return {
        "client_id": "selfrepair",
        "workspace_id": str(run.repo_id),
        "task_id": f"review-{run.id}-{finding.fingerprint[:12]}",
        "repo_url": repo_url,
        "branch": base_branch,
        "mode": mode,
        "issues": [
            {
                "id": finding.fingerprint[:32],
                "severity": severity,
                "description": finding.description[:2000],
                "recommended_action": (finding.suggested_fix or finding.title)[:2000],
            }
        ],
        "allowed_paths": [finding.file_path],
        "forbidden_paths": list(_FORBIDDEN),
        "coder": {"provider": "ollabridge", "model": "code-coder"},
        "sandbox": {"provider": "matrixlab", "profile": "default", "required": True},
        "human_approval": bool(human_approved),
        "auto_merge": False,
    }


def submit_repair_plan(plan: dict[str, Any], client: Any) -> Any:
    """Send a plan through the existing GitPilot coder client.

    `client` is `selfrepair.coders.gitpilot_client.GitPilotClient` or a fake
    with the same `repair(plan, dry_run=...)` method. This function does not
    merge.
    """
    if plan.get("auto_merge"):
        raise RemediationRefused("auto_merge is not permitted")
    if not plan.get("allowed_paths"):
        raise RemediationRefused("empty allowed_paths")
    dry_run = plan.get("mode") != "draft_pr"
    return client.repair(plan, dry_run=dry_run)


def new_task_id() -> str:
    """A unique task id for callers that build plans outside a review run."""
    return f"review-{uuid.uuid4()}"
