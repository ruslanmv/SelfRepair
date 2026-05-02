"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-01

"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "org",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("plan", sa.String(64), nullable=False, server_default="free"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "user_account",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "reviewer", "viewer", name="user_role"),
            nullable=False, server_default="viewer",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "email"),
    )
    op.create_index("ix_user_account_org_id", "user_account", ["org_id"])

    op.create_table(
        "repo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("default_branch", sa.String(255), nullable=False, server_default="main"),
        sa.Column("last_seen_sha", sa.String(64)),
        sa.Column("config_yaml", sa.Text()),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("org_id", "provider", "full_name"),
    )
    op.create_index("ix_repo_org_id", "repo", ["org_id"])

    job_state = sa.Enum(
        "queued", "cloning", "analyzing", "scanning", "planning",
        "repairing", "validating", "publishing", "awaiting_review",
        "completed", "failed_validation", "escalated",
        "merged", "closed", "stale",
        name="job_state",
    )
    job_trigger = sa.Enum(
        "scheduled", "webhook", "manual", "retry", name="job_trigger"
    )

    op.create_table(
        "job",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "repo_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repo.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("trigger", job_trigger, nullable=False),
        sa.Column("state", job_state, nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("sandbox_id", sa.String(128)),
        sa.Column("error_kind", sa.String(128)),
    )
    op.create_index("ix_job_org_id", "job", ["org_id"])
    op.create_index("ix_job_repo_id", "job", ["repo_id"])
    op.create_index("ix_job_state", "job", ["state"])

    op.create_table(
        "job_event",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stage", job_state, nullable=False),
        sa.Column("level", sa.String(16), nullable=False, server_default="info"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", postgresql.JSONB()),
    )
    op.create_index("ix_job_event_job_id", "job_event", ["job_id"])

    finding_status = sa.Enum(
        "open", "fixed", "wont_fix", "suppressed", name="finding_status"
    )
    op.create_table(
        "finding",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "repo_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repo.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(255), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("cwe", sa.String(32)),
        sa.Column("cve", sa.String(32)),
        sa.Column("first_seen_sha", sa.String(64)),
        sa.Column("last_seen_sha", sa.String(64)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", finding_status, nullable=False, server_default="open"),
        sa.Column("suppressed_until", sa.DateTime(timezone=True)),
        sa.Column("suppressed_reason", sa.Text()),
        sa.Column("metadata", postgresql.JSONB()),
        sa.UniqueConstraint(
            "org_id", "repo_id", "fingerprint", name="uq_finding_fingerprint"
        ),
    )
    op.create_index("ix_finding_org_id", "finding", ["org_id"])
    op.create_index("ix_finding_repo_id", "finding", ["repo_id"])
    op.create_index("ix_finding_kind", "finding", ["kind"])
    op.create_index("ix_finding_repo_status", "finding", ["repo_id", "status"])

    repair_mode = sa.Enum("deterministic", "llm", name="repair_mode")
    repair_state = sa.Enum(
        "planned", "applied", "validated", "published",
        "merged", "reverted", "failed",
        name="repair_state",
    )
    op.create_table(
        "repair",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "finding_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("finding.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "job_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("fixer_id", sa.String(255), nullable=False),
        sa.Column("mode", repair_mode, nullable=False),
        sa.Column("model_id", sa.String(128)),
        sa.Column("prompt_hash", sa.String(64)),
        sa.Column("diff_sha", sa.String(64)),
        sa.Column("sandbox_result", postgresql.JSONB()),
        sa.Column("signed_commit_sha", sa.String(64)),
        sa.Column("pr_url", sa.String(512)),
        sa.Column("state", repair_state, nullable=False, server_default="planned"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
    )
    op.create_index("ix_repair_finding_id", "repair", ["finding_id"])
    op.create_index("ix_repair_job_id", "repair", ["job_id"])

    op.create_table(
        "policy_decision",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "repair_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repair.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("rule_id", sa.String(255), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column(
            "requires_approval", sa.Boolean(),
            nullable=False, server_default=sa.text("false"),
        ),
        sa.Column(
            "approver_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.id", ondelete="SET NULL"),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_policy_decision_repair_id", "policy_decision", ["repair_id"])

    op.create_table(
        "provenance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "repair_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repair.id", ondelete="CASCADE"),
            nullable=False, unique=True,
        ),
        sa.Column("builder", sa.String(255), nullable=False),
        sa.Column("materials", postgresql.JSONB(), nullable=False),
        sa.Column("attestation_blob", sa.LargeBinary()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.String(64)),
        sa.Column("payload", postgresql.JSONB()),
    )
    op.create_index("ix_audit_log_org_id", "audit_log", ["org_id"])
    op.create_index("ix_audit_log_ts", "audit_log", ["ts"])


def downgrade() -> None:
    for table in (
        "audit_log", "provenance", "policy_decision", "repair",
        "finding", "job_event", "job", "repo", "user_account", "org",
    ):
        op.drop_table(table)
    bind = op.get_bind()
    for enum_name in (
        "repair_state", "repair_mode", "finding_status",
        "job_state", "job_trigger", "user_role",
    ):
        sa.Enum(name=enum_name).drop(bind, checkfirst=False)
