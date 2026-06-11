"""Repair plan aggregation.

Aggregates detector issues into a repair-plan that SelfRepair hands to GitPilot
(which writes code) and MatrixLab (which validates). SelfRepair itself NEVER
writes code -- this module only produces a plan dict/model.

The emitted JSON shape is a SHARED CONTRACT with the other ecosystem repos:

    {
      client_id, workspace_id, task_id, repo_url, branch,
      mode: "dry_run",
      health_score,
      issues: [{id, severity, description, recommended_action}],
      allowed_paths: [...],           # DERIVED from the detected issues
      forbidden_paths: [".env", "secrets/**", "**/*token*", "**/*secret*"],
      coder:   {provider: "gitpilot",  model: "code-coder"},
      sandbox: {provider: "matrixlab", profile: "python-repair", required: true}
    }
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from selfrepair.analyzers.repo_analyzer import (
    RECOMMENDED_FILES,
    SEVERITY_WEIGHTS,
    AnalysisResult,
    Issue,
)

# Default forbidden paths are constant across clients: a repair must never be
# allowed to touch secrets/credentials regardless of detected issues.
DEFAULT_FORBIDDEN_PATHS: list[str] = [
    ".env",
    "secrets/**",
    "**/*token*",
    "**/*secret*",
]


class IssueModel(BaseModel):
    id: str
    severity: str
    description: str
    recommended_action: str


class CoderSpec(BaseModel):
    provider: str = "gitpilot"
    model: str = "code-coder"


class SandboxSpec(BaseModel):
    provider: str = "matrixlab"
    profile: str = "python-repair"
    required: bool = True


class RepairPlan(BaseModel):
    client_id: str
    workspace_id: str
    task_id: str
    repo_url: str
    branch: str
    mode: str = "dry_run"
    health_score: int
    issues: list[IssueModel] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    forbidden_paths: list[str] = Field(default_factory=lambda: list(DEFAULT_FORBIDDEN_PATHS))
    coder: CoderSpec = Field(default_factory=CoderSpec)
    sandbox: SandboxSpec = Field(default_factory=SandboxSpec)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def compute_health_score(issues: list[Issue]) -> int:
    """Compute a 0-100 health score from issue severities.

    100 == perfectly healthy. Each issue subtracts its severity weight; the
    score is clamped to the [0, 100] range.
    """
    penalty = sum(SEVERITY_WEIGHTS.get(issue.severity, 10) for issue in issues)
    return max(0, min(100, 100 - penalty))


def derive_allowed_paths(issues: list[Issue]) -> list[str]:
    """Derive allowed_paths from the files each issue's repair would touch.

    Deterministic and de-duplicated while preserving first-seen order.
    """
    seen: set[str] = set()
    allowed: list[str] = []
    for issue in issues:
        for path in RECOMMENDED_FILES.get(issue.id, []):
            if path not in seen:
                seen.add(path)
                allowed.append(path)
    return allowed


def _coerce_issues(
    issues: list[Issue] | AnalysisResult | list[dict[str, Any]],
) -> list[Issue]:
    if isinstance(issues, AnalysisResult):
        return list(issues.issues)
    coerced: list[Issue] = []
    for item in issues:
        if isinstance(item, Issue):
            coerced.append(item)
        elif isinstance(item, dict):
            coerced.append(
                Issue(
                    id=item["id"],
                    severity=item.get("severity", "medium"),
                    description=item.get("description", ""),
                    recommended_action=item.get("recommended_action", ""),
                )
            )
    return coerced


def build_repair_plan(
    *,
    repo_url: str,
    issues: list[Issue] | AnalysisResult | list[dict[str, Any]],
    client_id: str,
    workspace_id: str,
    branch: str = "main",
    task_id: str | None = None,
    mode: str = "dry_run",
    coder_provider: str = "gitpilot",
    coder_model: str = "code-coder",
    sandbox_provider: str = "matrixlab",
    sandbox_profile: str = "python-repair",
    sandbox_required: bool = True,
    extra_allowed_paths: list[str] | None = None,
    planner_hint: dict[str, Any] | None = None,
) -> RepairPlan:
    """Aggregate detector issues into a RepairPlan.

    ``planner_hint`` is an optional, already-resolved suggestion from the
    repo-planner LLM (the caller decides whether to consult it). When absent we
    derive everything deterministically so the plan works fully offline.
    """
    issue_list = _coerce_issues(issues)
    health_score = compute_health_score(issue_list)
    allowed = derive_allowed_paths(issue_list)

    if planner_hint:
        for path in planner_hint.get("allowed_paths", []) or []:
            if path not in allowed:
                allowed.append(path)
    for path in extra_allowed_paths or []:
        if path not in allowed:
            allowed.append(path)

    return RepairPlan(
        client_id=client_id,
        workspace_id=workspace_id,
        task_id=task_id or f"task-{uuid.uuid4().hex[:12]}",
        repo_url=repo_url,
        branch=branch,
        mode=mode,
        health_score=health_score,
        issues=[IssueModel(**i.to_dict()) for i in issue_list],
        allowed_paths=allowed,
        forbidden_paths=list(DEFAULT_FORBIDDEN_PATHS),
        coder=CoderSpec(provider=coder_provider, model=coder_model),
        sandbox=SandboxSpec(
            provider=sandbox_provider, profile=sandbox_profile, required=sandbox_required
        ),
    )
