"""Review events, findings, and run records.

These are the in-process contracts. Persistence maps them onto the review
tables; publishers map them onto GitHub and GitLab payloads. They are not
repair findings.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CHECK_NAME = "SelfRepair / Review"
ZERO_SHA = "0" * 40

Severity = Literal["critical", "high", "medium", "low", "info"]
Category = Literal["security", "correctness", "architecture", "testing"]
Conclusion = Literal["success", "failure", "action_required", "neutral", "cancelled"]
RunStatus = Literal[
    "queued", "running", "completed", "incomplete", "skipped", "superseded", "failed"
]
EngineName = Literal["deterministic", "deepagents", "llm"]


class CommitInfo(BaseModel):
    """One commit inside a push, kept for traceability. Not its own review."""

    model_config = ConfigDict(extra="ignore")

    sha: str
    message: str = ""


class ReviewEvent(BaseModel):
    """A normalized repository-change event, independent of the provider."""

    model_config = ConfigDict(extra="ignore")

    provider: Literal["github", "gitlab"]
    kind: Literal["push", "pull_request", "merge_request"]
    action: str | None = None
    delivery_id: str
    repo_full_name: str
    installation_id: int | None = None
    project_id: int | None = None
    ref: str | None = None
    branch: str
    base_branch: str | None = None
    base_sha: str
    head_sha: str
    forced: bool = False
    deleted: bool = False
    commits: list[CommitInfo] = Field(default_factory=list)
    pr_number: int | None = None
    from_fork: bool = False
    sender_login: str | None = None
    sender_type: str | None = None
    default_branch: str = "main"
    compare_url: str | None = None
    title: str | None = None
    draft: bool = False
    # What started this review, as shown in the pull-request status comment:
    # "PR opened", "Ready for review", "New commits", "@user", "Retry".
    trigger: str | None = None
    # The comment that asked for the review (`@selfrepair review`), if any.
    trigger_comment_id: int | None = None


class DiffLine(BaseModel):
    """One changed line that an inline comment is allowed to target."""

    path: str
    line: int
    side: Literal["RIGHT", "LEFT"]
    text: str


class DiffFile(BaseModel):
    """A file in the reviewed change set."""

    path: str
    previous_path: str | None = None
    status: Literal["added", "modified", "removed", "renamed", "binary"] = "modified"
    patch: str = ""
    lines: list[DiffLine] = Field(default_factory=list)


class DiffSet(BaseModel):
    """The diff a review is allowed to cite."""

    files: list[DiffFile] = Field(default_factory=list)
    truncated: bool = False
    source: str = "unavailable"
    error: str | None = None

    def changed_paths(self) -> list[str]:
        return [item.path for item in self.files]


class FindingDraft(BaseModel):
    """A candidate finding before line validation and fingerprinting."""

    model_config = ConfigDict(extra="ignore")

    category: Category
    severity: Severity
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    file_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    side: Literal["RIGHT", "LEFT"] | None = "RIGHT"
    title: str
    description: str
    evidence: str | None = None
    suggested_fix: str | None = None
    source: Literal["deterministic", "deepagents", "llm"] = "deterministic"


class FindingRecord(FindingDraft):
    """A finding that survived validation."""

    fingerprint: str
    validation_state: Literal["accepted", "rejected"] = "accepted"
    resolution_state: str = "open"


class ReviewReport(BaseModel):
    """The engine's result before policy assigns the check conclusion."""

    summary: str
    findings: list[FindingDraft] = Field(default_factory=list)
    model_id: str | None = None
    engine: EngineName = "deterministic"
    incomplete_reason: str | None = None


class RunRecord(BaseModel):
    """A durable review run, as returned by both stores."""

    id: uuid.UUID
    org_id: uuid.UUID
    repo_id: uuid.UUID
    provider: str
    event_type: str
    delivery_id: str | None = None
    ref: str | None = None
    pr_number: int | None = None
    base_sha: str
    head_sha: str
    forced: bool = False
    from_fork: bool = False
    engine: str
    model_id: str | None = None
    policy_version: str
    status: str
    conclusion: str | None = None
    summary: str | None = None
    error: str | None = None
    sender_login: str | None = None
    commit_shas: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class RepoBinding(BaseModel):
    """The tenant row a webhook resolved to."""

    org_id: uuid.UUID
    repo_id: uuid.UUID
    provider: str
    full_name: str
    default_branch: str
    config_yaml: str | None = None
    installation_id: int | None = None
    ambiguous: bool = False


class PublicationDraft(BaseModel):
    """A provider payload that has not yet been sent."""

    provider: str
    kind: Literal["check", "review", "discussion", "status"]
    body: dict[str, Any]
    fingerprints: list[str] = Field(default_factory=list)


class EngineUnavailable(RuntimeError):
    """The selected engine cannot run. Callers must not report success."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class TransientReviewError(RuntimeError):
    """A retryable provider or network failure. The check must stay incomplete."""
