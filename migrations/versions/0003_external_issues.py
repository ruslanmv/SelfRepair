"""issue_watch: external_issue / external_issue_action + JobTrigger.issue

Revision ID: 0003_external_issues
Revises: 0002_ci_guardian
Create Date: 2026-05-02

Strictly additive:
  * Adds the 'issue' value to the existing job_trigger enum. ALTER TYPE is
    wrapped in autocommit_block so it's safe on Postgres < 12 too.
  * Adds two new tables, `external_issue` and `external_issue_action`, plus
    a new `external_issue_action_type` enum.

Nothing existing is touched. The `JobTrigger.ISSUE` value lets Issue Watch
enqueue normal SelfRepair jobs through the existing pipeline rather than
spawning a parallel one.

Downgrade caveat (mirrors 0002): Postgres can't drop enum values, so the
'issue' value on job_trigger stays after a downgrade. Harmless: no rows
reference it once external_issue_action is gone.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_external_issues"
down_revision: Union[str, Sequence[str], None] = "0002_ci_guardian"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE job_trigger ADD VALUE IF NOT EXISTS 'issue'"
        )

    action_type = sa.Enum(
        "sync",
        "triage",
        "create_finding",
        "run_repair",
        "comment",
        "suppress",
        "link_existing_repair",
        "close_external_issue",
        name="external_issue_action_type",
    )

    op.create_table(
        "external_issue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "repo_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repo.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_issue_id", sa.String(128), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body_excerpt", sa.Text()),
        sa.Column("state", sa.String(32), nullable=False, server_default="open"),
        sa.Column("author", sa.String(255)),
        sa.Column("labels", postgresql.JSONB(), server_default="[]"),
        sa.Column("assignees", postgresql.JSONB(), server_default="[]"),
        sa.Column("priority", sa.String(32)),
        sa.Column("repair_class", sa.String(64)),
        sa.Column("repairable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("html_url", sa.Text()),
        sa.Column("created_at_external", sa.DateTime(timezone=True)),
        sa.Column("updated_at_external", sa.DateTime(timezone=True)),
        sa.Column("closed_at_external", sa.DateTime(timezone=True)),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("raw", postgresql.JSONB()),
        sa.UniqueConstraint(
            "org_id", "provider", "provider_issue_id",
            name="uq_external_issue_provider_id",
        ),
    )
    op.create_index("ix_external_issue_repo_id", "external_issue", ["repo_id"])
    op.create_index(
        "ix_external_issue_dashboard", "external_issue",
        ["repo_id", "state", "updated_at_external"],
    )
    op.create_index(
        "ix_external_issue_priority", "external_issue", ["org_id", "priority"]
    )

    op.create_table(
        "external_issue_action",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "external_issue_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("external_issue.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "action_type", action_type,
            nullable=False,
        ),
        sa.Column(
            "action_status", sa.String(32),
            nullable=False, server_default="pending",
        ),
        sa.Column("actor", sa.String(255)),
        sa.Column(
            "job_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "finding_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("finding.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "repair_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repair.id", ondelete="SET NULL"),
        ),
        sa.Column("comment_url", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB()),
    )
    op.create_index(
        "ix_external_issue_action_issue_id",
        "external_issue_action", ["external_issue_id"],
    )
    op.create_index(
        "ix_external_issue_action_org_created",
        "external_issue_action", ["org_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("external_issue_action")
    op.drop_table("external_issue")
    op.execute("DROP TYPE IF EXISTS external_issue_action_type")
    # The 'issue' value on the job_trigger enum stays — Postgres can't drop
    # enum values. Harmless after the action table is gone.
