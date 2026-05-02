"""ORM models for jobs, findings, repairs, audit, provenance, and CI Guardian.

Schema design: docs/architecture/system-design.md §4 + the CI Guardian plan.

Core invariants:
- `org_id` on every tenant table (tenancy as a row, not a deployment).
- Findings carry stable fingerprints; (org_id, repo_id, fingerprint) is unique.
- Repairs are separate from findings; multiple attempts per finding are normal.
- CI failures carry stable fingerprints; (repo_id, fingerprint) is unique.
- Audit log is append-only; partitioning by month is configured in migrations.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from selfrepair.persistence.db import Base
from selfrepair.state.machine import JobState


def value_enum(enum_cls: type[StrEnum], *, name: str) -> SqlEnum:
    """SqlEnum that persists the StrEnum *value*, not its NAME.

    SQLAlchemy's default for `SqlEnum(SomeStrEnum)` derives DB labels from
    member names (uppercase). Our migrations declare lowercase values, so
    we route every column through `values_callable` to keep ORM and DDL
    aligned. This avoids the migration-vs-ORM drift CI was catching.
    """
    return SqlEnum(
        enum_cls,
        name=name,
        values_callable=lambda cls: [member.value for member in cls],
    )


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _utcnow() -> datetime:
    return datetime.now(UTC)


# -------------------- Tenancy --------------------


class UserRole(StrEnum):
    ADMIN = "admin"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class Org(Base):
    __tablename__ = "org"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(64), default="free", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class User(Base):
    # `user` is reserved in Postgres.
    __tablename__ = "user_account"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        value_enum(UserRole, name="user_role"), default=UserRole.VIEWER, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (UniqueConstraint("org_id", "email"),)


# -------------------- Inventory --------------------


class Repo(Base):
    __tablename__ = "repo"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)
    last_seen_sha: Mapped[str | None] = mapped_column(String(64))
    config_yaml: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("org_id", "provider", "full_name"),)


# -------------------- Jobs --------------------


class JobTrigger(StrEnum):
    SCHEDULED = "scheduled"
    WEBHOOK = "webhook"
    MANUAL = "manual"
    RETRY = "retry"
    # Additive in migration 0002 — the seam for CI Guardian to enqueue normal
    # repair jobs without forking a second pipeline.
    CI_FAILURE = "ci_failure"
    CI_VERIFICATION = "ci_verification"
    # Additive in migration 0003 — Issue Watch enqueues normal repair jobs
    # from external GitHub/GitLab/HF issues through the same pipeline.
    ISSUE = "issue"


class Job(Base):
    __tablename__ = "job"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repo.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    trigger: Mapped[JobTrigger] = mapped_column(
        value_enum(JobTrigger, name="job_trigger"), nullable=False
    )
    state: Mapped[JobState] = mapped_column(
        value_enum(JobState, name="job_state"),
        default=JobState.QUEUED, nullable=False, index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sandbox_id: Mapped[str | None] = mapped_column(String(128))
    error_kind: Mapped[str | None] = mapped_column(String(128))


class JobEvent(Base):
    __tablename__ = "job_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    stage: Mapped[JobState] = mapped_column(
        value_enum(JobState, name="job_state"), nullable=False
    )
    level: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


# -------------------- Findings --------------------


class FindingStatus(StrEnum):
    OPEN = "open"
    FIXED = "fixed"
    WONT_FIX = "wont_fix"
    SUPPRESSED = "suppressed"


class Finding(Base):
    __tablename__ = "finding"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repo.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    cwe: Mapped[str | None] = mapped_column(String(32))
    cve: Mapped[str | None] = mapped_column(String(32))
    first_seen_sha: Mapped[str | None] = mapped_column(String(64))
    last_seen_sha: Mapped[str | None] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    status: Mapped[FindingStatus] = mapped_column(
        value_enum(FindingStatus, name="finding_status"),
        default=FindingStatus.OPEN, nullable=False,
    )
    suppressed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suppressed_reason: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)

    __table_args__ = (
        UniqueConstraint(
            "org_id", "repo_id", "fingerprint", name="uq_finding_fingerprint"
        ),
        Index("ix_finding_repo_status", "repo_id", "status"),
    )


# -------------------- Repairs --------------------


class RepairMode(StrEnum):
    DETERMINISTIC = "deterministic"
    LLM = "llm"


class RepairState(StrEnum):
    PLANNED = "planned"
    APPLIED = "applied"
    VALIDATED = "validated"
    PUBLISHED = "published"
    MERGED = "merged"
    REVERTED = "reverted"
    FAILED = "failed"


class Repair(Base):
    __tablename__ = "repair"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finding.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    fixer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[RepairMode] = mapped_column(
        value_enum(RepairMode, name="repair_mode"), nullable=False
    )
    model_id: Mapped[str | None] = mapped_column(String(128))
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    diff_sha: Mapped[str | None] = mapped_column(String(64))
    sandbox_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    signed_commit_sha: Mapped[str | None] = mapped_column(String(64))
    pr_url: Mapped[str | None] = mapped_column(String(512))
    state: Mapped[RepairState] = mapped_column(
        value_enum(RepairState, name="repair_state"),
        default=RepairState.PLANNED, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0, nullable=False)


# -------------------- Policy / Provenance / Audit --------------------


class PolicyDecision(Base):
    __tablename__ = "policy_decision"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    repair_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repair.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    rule_id: Mapped[str] = mapped_column(String(255), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Provenance(Base):
    __tablename__ = "provenance"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    repair_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repair.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    builder: Mapped[str] = mapped_column(String(255), nullable=False)
    materials: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    attestation_blob: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    ip: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


# -------------------- CI Guardian --------------------


class CIFailureStatus(StrEnum):
    """Lifecycle of a deduplicated CI failure.

    Transitions:
        open → rerun_queued → rerun_succeeded → resolved
        open → repair_queued → repair_opened → resolved
        open → suppressed | escalated
    Each transition writes an audit_log row (no new audit table).
    """

    OPEN = "open"
    RERUN_QUEUED = "rerun_queued"
    RERUN_SUCCEEDED = "rerun_succeeded"
    REPAIR_QUEUED = "repair_queued"
    REPAIR_OPENED = "repair_opened"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"
    ESCALATED = "escalated"


class CIWorkflowRun(Base):
    """One row per GitHub Actions workflow run + run_attempt.

    Webhooks may arrive multiple times for the same run; the unique
    constraint on (repo_id, github_run_id, run_attempt) makes the
    dispatcher's upsert idempotent.
    """

    __tablename__ = "ci_workflow_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repo.id", ondelete="CASCADE"),
        nullable=False,
    )
    github_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    github_workflow_id: Mapped[int | None] = mapped_column(BigInteger)
    workflow_name: Mapped[str | None] = mapped_column(Text)
    workflow_path: Mapped[str | None] = mapped_column(Text)
    head_sha: Mapped[str | None] = mapped_column(String(64))
    head_branch: Mapped[str | None] = mapped_column(Text)
    event: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text)
    run_attempt: Mapped[int | None] = mapped_column(Integer)
    html_url: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_event: Mapped[str | None] = mapped_column(Text)
    delivery_id: Mapped[str | None] = mapped_column(String(64))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint(
            "repo_id", "github_run_id", "run_attempt",
            name="uq_ci_run_attempt",
        ),
        Index("ix_ci_workflow_run_repo_sha", "repo_id", "head_sha"),
        Index(
            "ix_ci_workflow_run_dashboard",
            "org_id", "status", "completed_at",
        ),
    )


class CIWorkflowJob(Base):
    """One row per job inside a workflow run."""

    __tablename__ = "ci_workflow_job"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ci_workflow_run.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    github_job_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text, index=True)
    runner_name: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_step_name: Mapped[str | None] = mapped_column(Text)
    step_failure_index: Mapped[int | None] = mapped_column(Integer)
    log_excerpt: Mapped[str | None] = mapped_column(Text)
    log_object_key: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id", "github_job_id", name="uq_ci_workflow_job"
        ),
    )


class CIFailure(Base):
    """Deduplicated failure across runs, indexed by stable fingerprint.

    The fingerprint is computed from the normalized error signature so the
    same flake across many runs collapses to a single row with a growing
    `occurrence_count` rather than N rows.
    """

    __tablename__ = "ci_failure"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repo.id", ondelete="CASCADE"),
        nullable=False,
    )
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ci_workflow_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    workflow_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ci_workflow_job.id", ondelete="CASCADE")
    )
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finding.id", ondelete="SET NULL")
    )
    repair_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job.id", ondelete="SET NULL")
    )
    repair_pr_url: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    failure_class: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CIFailureStatus] = mapped_column(
        value_enum(CIFailureStatus, name="ci_failure_status"),
        default=CIFailureStatus.OPEN, nullable=False,
    )
    auto_action: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurrence_count: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    last_error_signature: Mapped[str | None] = mapped_column(Text)
    policy_decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    kill_switched: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    redacted_secret_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    diagnostic: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint(
            "repo_id", "fingerprint", name="uq_ci_failure_fingerprint"
        ),
        Index("ix_ci_failure_repo_status", "repo_id", "status"),
    )


# -------------------- Issue Watch (migration 0003) --------------------


class ExternalIssueActionType(StrEnum):
    """Mutating actions taken from the Open Issues surface.

    Mirrors the migration 0003 enum exactly; values are persisted, names
    are uppercase only in Python (see `value_enum`).
    """

    SYNC = "sync"
    TRIAGE = "triage"
    CREATE_FINDING = "create_finding"
    RUN_REPAIR = "run_repair"
    COMMENT = "comment"
    SUPPRESS = "suppress"
    LINK_EXISTING_REPAIR = "link_existing_repair"
    CLOSE_EXTERNAL_ISSUE = "close_external_issue"


class ExternalIssue(Base):
    """One human-created issue from GitHub Issues, GitLab Issues, or HF
    Community Discussions. Sync upserts on (org_id, provider,
    provider_issue_id); the original payload stays in `raw` so we can add
    columns later without re-shipping migrations.
    """

    __tablename__ = "external_issue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repo.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_issue_id: Mapped[str] = mapped_column(String(128), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body_excerpt: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    author: Mapped[str | None] = mapped_column(String(255))
    labels: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    assignees: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    priority: Mapped[str | None] = mapped_column(String(32))
    repair_class: Mapped[str | None] = mapped_column(String(64))
    repairable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    html_url: Mapped[str | None] = mapped_column(Text)
    created_at_external: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at_external: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at_external: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint(
            "org_id", "provider", "provider_issue_id",
            name="uq_external_issue_provider_id",
        ),
        Index(
            "ix_external_issue_dashboard",
            "repo_id", "state", "updated_at_external",
        ),
        Index("ix_external_issue_priority", "org_id", "priority"),
    )


class ExternalIssueAction(Base):
    """Audit row for every mutating action triggered from the Open Issues UI.

    `job_id` / `finding_id` / `repair_id` are the seams back into the
    existing pipeline: a "run repair" action creates a normal job and
    links forward to it.
    """

    __tablename__ = "external_issue_action"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("external_issue.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    action_type: Mapped[ExternalIssueActionType] = mapped_column(
        value_enum(ExternalIssueActionType, name="external_issue_action_type"),
        nullable=False,
    )
    action_status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False
    )
    actor: Mapped[str | None] = mapped_column(String(255))
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job.id", ondelete="SET NULL")
    )
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finding.id", ondelete="SET NULL")
    )
    repair_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repair.id", ondelete="SET NULL")
    )
    comment_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        Index(
            "ix_external_issue_action_org_created",
            "org_id", "created_at",
        ),
    )
