"""Turn accepted review findings into a GitPilot repair task.

The plan matches the live GitPilot `POST /repair` contract
(`gitpilot.repair.schema.RepairRequest`): dry-run unless remediation is
enabled and a human approved a draft, allowed paths limited to the findings'
files, and no auto-merge. Fork pull requests are refused. The review engine is
not given this client, and SelfRepair never approves, merges, or pushes.

A task is stored on the review run under `metadata["remediations"]`. The
record holds the plan (finding text and paths only), the approver, and the
parsed GitPilot result. It never holds a prompt, a token, or the raw response.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from selfrepair.config.repo_config import ReviewerConfig
from selfrepair.reviewer.schemas import FindingRecord, RunRecord

logger = logging.getLogger(__name__)

_FORBIDDEN = [".env", "secrets/**", "**/*token*", "**/*secret*", "migrations/**", "infra/prod/**"]
_PATCH_PREVIEW_LIMIT = 64_000
_SEVERITIES = {"low", "medium", "high", "critical"}


class RemediationRefused(Exception):
    """The finding cannot become a coding task."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _check_finding(finding: FindingRecord) -> None:
    if finding.validation_state != "accepted":
        raise RemediationRefused("finding was not accepted")
    if not finding.file_path or ".." in finding.file_path.split("/") or finding.file_path.startswith("/"):
        raise RemediationRefused("finding path is not a repository path")


def build_repair_plan_for_findings(
    *,
    run: RunRecord,
    findings: list[FindingRecord],
    repo_url: str,
    config: ReviewerConfig,
    human_approved: bool,
    base_branch: str = "main",
    allowed_paths: list[str] | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Build one `POST /repair` body for one or more findings of one run.

    `allowed_paths` defaults to the findings' files. A caller may narrow it,
    but every path must be one of those files. `mode` is `dry_run` until
    remediation is enabled and a human approved the task; `draft_pr` is the
    strongest mode this function emits. It never sets a merge flag.
    """
    if not config.remediation.enabled:
        raise RemediationRefused("remediation disabled")
    if config.remediation.auto_merge:  # pragma: no cover - the schema forbids it
        raise RemediationRefused("auto_merge is not permitted")
    if run.from_fork:
        raise RemediationRefused("fork pull requests are not remediated")
    if not findings:
        raise RemediationRefused("no findings selected")
    for finding in findings:
        _check_finding(finding)
    finding_paths = sorted({str(item.file_path) for item in findings})
    if allowed_paths is None:
        paths = finding_paths
    else:
        paths = sorted(set(allowed_paths))
        if not paths:
            raise RemediationRefused("empty allowed_paths")
        outside = [path for path in paths if path not in finding_paths]
        if outside:
            raise RemediationRefused(f"paths outside the finding files: {', '.join(outside)}")
    if not paths:
        raise RemediationRefused("empty allowed_paths")
    mode = "draft_pr" if human_approved else "dry_run"
    if task_id is None:
        digest = hashlib.sha256(
            "|".join(sorted(item.fingerprint for item in findings)).encode()
        ).hexdigest()[:12]
        task_id = f"review-{run.id}-{digest}"
    return {
        "client_id": "selfrepair",
        "workspace_id": str(run.repo_id),
        "task_id": task_id,
        "repo_url": repo_url,
        "branch": base_branch,
        "mode": mode,
        "issues": [
            {
                "id": item.fingerprint[:32],
                "severity": item.severity if item.severity in _SEVERITIES else "medium",
                "description": item.description[:2000],
                "recommended_action": (item.suggested_fix or item.title)[:2000],
            }
            for item in findings
        ],
        "allowed_paths": paths,
        "forbidden_paths": list(_FORBIDDEN),
        "coder": {"provider": "ollabridge", "model": "code-coder"},
        "sandbox": {"provider": "matrixlab", "profile": "default", "required": True},
        "human_approval": bool(human_approved),
        "auto_merge": False,
    }


def build_repair_plan(
    *,
    run: RunRecord,
    finding: FindingRecord,
    repo_url: str,
    config: ReviewerConfig,
    human_approved: bool,
    base_branch: str = "main",
) -> dict[str, Any]:
    """Build a repair-plan body for a single finding. See `build_repair_plan_for_findings`."""
    if not config.remediation.enabled:
        raise RemediationRefused("remediation disabled")
    if run.from_fork:
        raise RemediationRefused("fork pull requests are not remediated")
    _check_finding(finding)
    return build_repair_plan_for_findings(
        run=run,
        findings=[finding],
        repo_url=repo_url,
        config=config,
        human_approved=human_approved,
        base_branch=base_branch,
        task_id=f"review-{run.id}-{finding.fingerprint[:12]}",
    )


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


# ---------------------------------------------------------------------------
# Review-run tasks: the explicit, tenant-scoped action used by the API/worker.
# ---------------------------------------------------------------------------


def repo_url_for(run: RunRecord) -> str:
    """Clone URL GitPilot is given. It carries no credential."""
    full_name = str((run.metadata or {}).get("repo_full_name") or "")
    if not full_name:
        raise RemediationRefused("review has no repository name")
    if run.provider == "gitlab":
        base = (os.getenv("GITLAB_URL") or "https://gitlab.com").rstrip("/")
        return f"{base}/{full_name}"
    return f"https://github.com/{full_name}"


def gitpilot_client_from_env() -> Any:
    """The live `POST /repair` client, configured from the environment."""
    from selfrepair.coders.gitpilot_client import GitPilotClient

    url = os.getenv("SELFREPAIR_GITPILOT_URL") or os.getenv("GITPILOT_URL") or None
    token = os.getenv("SELFREPAIR_GITPILOT_TOKEN") or os.getenv("GITPILOT_API_TOKEN") or None
    return GitPilotClient(url or "http://localhost:9000", token=token, timeout=300.0)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def list_tasks(run: RunRecord) -> list[dict[str, Any]]:
    return [dict(item) for item in (run.metadata or {}).get("remediations") or []]


async def _save_task(store: Any, run_id: uuid.UUID, task: dict[str, Any]) -> dict[str, Any]:
    fresh = await store.get_run(run_id)
    if fresh is None:
        raise RemediationRefused("review not found")
    metadata = dict(fresh.metadata or {})
    tasks = [item for item in metadata.get("remediations") or [] if item.get("id") != task["id"]]
    tasks.append(task)
    metadata["remediations"] = tasks
    await store.update_run(run_id, metadata=metadata)
    return task


async def create_task(
    *,
    store: Any,
    run: RunRecord,
    config: ReviewerConfig,
    fingerprints: list[str],
    allowed_paths: list[str] | None,
    approve: bool,
    requested_by: str | None,
    auto_merge: bool = False,
) -> dict[str, Any]:
    """Validate a request and store a `queued` task with its plan.

    `approve` is a human decision recorded with `requested_by`. Without it the
    task is a dry run, whatever the config says.
    """
    if auto_merge:
        raise RemediationRefused("auto_merge is not permitted")
    if not fingerprints:
        raise RemediationRefused("no findings selected")
    if run.status == "superseded":
        raise RemediationRefused("review was superseded by a newer head")
    findings = await store.list_findings(run.id)
    by_fp = {item.fingerprint: item for item in findings}
    missing = [fp for fp in fingerprints if fp not in by_fp]
    if missing:
        raise RemediationRefused("unknown finding for this review")
    selected = [by_fp[fp] for fp in dict.fromkeys(fingerprints)]
    human_approved = bool(approve and requested_by)
    meta = run.metadata or {}
    plan = build_repair_plan_for_findings(
        run=run,
        findings=selected,
        repo_url=repo_url_for(run),
        config=config,
        human_approved=human_approved,
        base_branch=str(meta.get("branch") or "main"),
        allowed_paths=allowed_paths,
        # One id per request, so a later approval never overwrites the dry run
        # it followed. GitPilot works on branch `gitpilot/<task_id>`.
        task_id=f"review-{run.id.hex[:12]}-{uuid.uuid4().hex[:12]}",
    )
    task = {
        "id": plan["task_id"],
        "status": "queued",
        "mode": plan["mode"],
        "fingerprints": [item.fingerprint for item in selected],
        "allowed_paths": plan["allowed_paths"],
        "approved": human_approved,
        "requested_by": requested_by,
        "requested_at": _now(),
        "plan": plan,
        "result": None,
        "error": None,
    }
    return await _save_task(store, run.id, task)


def _result_summary(response: Any) -> tuple[str, dict[str, Any]]:
    """Reduce a GitPilot response to what the review record keeps."""
    raw = getattr(response, "raw", None)
    if raw is None and isinstance(response, dict):
        raw = response
    raw = raw if isinstance(raw, dict) else {}
    stubbed = bool(getattr(response, "stubbed", False) or raw.get("stub"))
    gp_status = str(getattr(response, "status", None) or raw.get("status") or "unknown")
    patch = str(getattr(response, "patch_preview", None) or raw.get("patch_preview") or "")
    changed = getattr(response, "changed_files", None)
    if changed is None:
        changed = [
            item.get("path") if isinstance(item, dict) else item
            for item in raw.get("changed_files") or []
        ]
    review = getattr(response, "review", None) if not isinstance(response, dict) else raw.get("review")
    summary = {
        "status": gp_status,
        "risk_level": str(getattr(response, "risk_level", None) or raw.get("risk_level") or ""),
        "changed_files": [str(item) for item in changed or [] if item],
        "patch_preview": patch[:_PATCH_PREVIEW_LIMIT],
        "patch_truncated": len(patch) > _PATCH_PREVIEW_LIMIT,
        "review": review if isinstance(review, str) else None,
        "pr_url": raw.get("pr_url"),
        "warnings": [str(item) for item in raw.get("warnings") or []][:20],
        "stubbed": stubbed,
    }
    if stubbed:
        return "gitpilot_unavailable", summary
    if gp_status in {"ok", "dry_run"}:
        return "completed", summary
    if gp_status in {"blocked", "needs_approval"}:
        return gp_status, summary
    return "failed", summary


async def execute_task(
    *, store: Any, review_id: uuid.UUID, task_id: str, client: Any | None = None
) -> dict[str, Any]:
    """Send one queued task to GitPilot `POST /repair` and store the outcome.

    An unreachable GitPilot (the client's offline stub) is recorded as
    `gitpilot_unavailable`, never as a produced patch.
    """
    run = await store.get_run(review_id)
    if run is None:
        raise RemediationRefused("review not found")
    task = next((item for item in list_tasks(run) if item.get("id") == task_id), None)
    if task is None:
        raise RemediationRefused("remediation task not found")
    if task.get("status") not in {"queued", "gitpilot_unavailable", "failed"}:
        return task
    plan = dict(task.get("plan") or {})
    task = dict(task, status="running", started_at=_now())
    await _save_task(store, review_id, task)
    try:
        # The live client is synchronous httpx; keep the worker loop free.
        response = await asyncio.to_thread(
            submit_repair_plan, plan, client or gitpilot_client_from_env()
        )
    except RemediationRefused as exc:
        task.update(status="refused", error=exc.reason, completed_at=_now())
        return await _save_task(store, review_id, task)
    except Exception as exc:  # network or schema error; keep the type only
        logger.warning("gitpilot remediation failed task=%s error=%s", task_id, type(exc).__name__)
        task.update(status="failed", error=type(exc).__name__, completed_at=_now())
        return await _save_task(store, review_id, task)
    status, summary = _result_summary(response)
    task.update(
        status=status,
        result=summary,
        error="GitPilot did not answer; no patch was produced" if summary["stubbed"] else None,
        completed_at=_now(),
    )
    return await _save_task(store, review_id, task)


def public_task(task: dict[str, Any]) -> dict[str, Any]:
    """API view of a task. The plan is shown; it holds no prompt or token."""
    return {
        key: task.get(key)
        for key in (
            "id",
            "status",
            "mode",
            "fingerprints",
            "allowed_paths",
            "approved",
            "requested_by",
            "requested_at",
            "started_at",
            "completed_at",
            "result",
            "error",
            "plan",
        )
    }
