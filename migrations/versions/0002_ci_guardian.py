"""ci_guardian: workflow_run / workflow_job / failure tables + JobTrigger extension

Revision ID: 0002_ci_guardian
Revises: 0001_initial
Create Date: 2026-05-02

Non-destructive: only adds new tables, indexes, an enum type, and two
enum values to the existing job_trigger type. The existing schema is
untouched.

Note on downgrade: Postgres does not support removing values from an
enum, so the `ci_failure` and `ci_verification` values added to
job_trigger remain after a downgrade. This is a known Postgres
limitation; if a hard rollback is needed, drop and recreate the type.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_ci_guardian"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ADD VALUE works inside a transaction since Postgres 12,
    # but Alembic's autocommit_block keeps us safe on older clusters too.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE job_trigger ADD VALUE IF NOT EXISTS 'ci_failure'"
        )
        op.execute(
            "ALTER TYPE job_trigger ADD VALUE IF NOT EXISTS 'ci_verification'"
        )

    ci_failure_status = sa.Enum(
        "open",
        "rerun_queued",
        "rerun_succeeded",
        "repair_queued",
        "repair_opened",
        "resolved",
        "suppressed",
        "escalated",
        name="ci_failure_status",
    )

    op.create_table(
        "ci_workflow_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "repo_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repo.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("github_run_id", sa.BigInteger(), nullable=False),
        sa.Column("github_workflow_id", sa.BigInteger()),
        sa.Column("workflow_name", sa.Text()),
        sa.Column("workflow_path", sa.Text()),
        sa.Column("head_sha", sa.String(64)),
        sa.Column("head_branch", sa.Text()),
        sa.Column("event", sa.Text()),
        sa.Column("status", sa.Text()),
        sa.Column("conclusion", sa.Text()),
        sa.Column("run_attempt", sa.Integer()),
        sa.Column("html_url", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_event", sa.Text()),
        sa.Column("delivery_id", sa.String(64)),
        sa.Column("raw", postgresql.JSONB()),
        sa.UniqueConstraint(
            "repo_id", "github_run_id", "run_attempt",
            name="uq_ci_run_attempt",
        ),
    )
    op.create_index(
        "ix_ci_workflow_run_org_id", "ci_workflow_run", ["org_id"]
    )
    op.create_index(
        "ix_ci_workflow_run_repo_sha", "ci_workflow_run", ["repo_id", "head_sha"]
    )
    op.create_index(
        "ix_ci_workflow_run_dashboard", "ci_workflow_run",
        ["org_id", "status", "completed_at"],
    )

    op.create_table(
        "ci_workflow_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workflow_run_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ci_workflow_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("github_job_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("status", sa.Text()),
        sa.Column("conclusion", sa.Text()),
        sa.Column("runner_name", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failed_step_name", sa.Text()),
        sa.Column("step_failure_index", sa.Integer()),
        sa.Column("log_excerpt", sa.Text()),
        sa.Column("log_object_key", sa.Text()),
        sa.Column("raw", postgresql.JSONB()),
        sa.UniqueConstraint(
            "workflow_run_id", "github_job_id", name="uq_ci_workflow_job"
        ),
    )
    op.create_index(
        "ix_ci_workflow_job_run_id", "ci_workflow_job", ["workflow_run_id"]
    )
    op.create_index(
        "ix_ci_workflow_job_conclusion", "ci_workflow_job", ["conclusion"]
    )

    op.create_table(
        "ci_failure",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "repo_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repo.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "workflow_run_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ci_workflow_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_job_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ci_workflow_job.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "finding_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("finding.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "repair_job_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job.id", ondelete="SET NULL"),
        ),
        sa.Column("repair_pr_url", sa.Text()),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("failure_class", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column(
            "status", ci_failure_status,
            nullable=False, server_default="open",
        ),
        sa.Column("auto_action", sa.Text()),
        sa.Column("confidence", sa.Numeric(3, 2)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "occurrence_count", sa.Integer(),
            nullable=False, server_default="1",
        ),
        sa.Column("last_error_signature", sa.Text()),
        sa.Column("policy_decision", postgresql.JSONB()),
        sa.Column(
            "kill_switched", sa.Boolean(),
            nullable=False, server_default=sa.text("false"),
        ),
        sa.Column(
            "redacted_secret_count", sa.Integer(),
            nullable=False, server_default="0",
        ),
        sa.Column("diagnostic", postgresql.JSONB()),
        sa.UniqueConstraint(
            "repo_id", "fingerprint", name="uq_ci_failure_fingerprint"
        ),
    )
    op.create_index("ix_ci_failure_org_id", "ci_failure", ["org_id"])
    op.create_index(
        "ix_ci_failure_repo_status", "ci_failure", ["repo_id", "status"]
    )
    op.create_index("ix_ci_failure_class", "ci_failure", ["failure_class"])
    op.create_index("ix_ci_failure_last_seen", "ci_failure", ["last_seen_at"])


def downgrade() -> None:
    op.drop_table("ci_failure")
    op.drop_table("ci_workflow_job")
    op.drop_table("ci_workflow_run")
    sa.Enum(name="ci_failure_status").drop(op.get_bind(), checkfirst=False)
    # The 'ci_failure' and 'ci_verification' values on the job_trigger enum
    # cannot be removed without dropping and recreating the type. We leave
    # them in place; they have no effect when no job rows reference them.
