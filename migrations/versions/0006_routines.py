"""branch-aware automation routines

Revision ID: 0006_routines
Revises: 0005_auth
Create Date: 2026-09-23

Strictly additive. Adds routine definitions and run history. It does not alter
existing schedules, jobs, repairs, or provider credentials.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_routines"
down_revision: Union[str, Sequence[str], None] = "0005_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "automation_routine",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repo.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("schedule_time", sa.String(5), nullable=False, server_default="08:00"),
        sa.Column(
            "schedule_days",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("source_branch", sa.String(255), nullable=False),
        sa.Column("target_branch", sa.String(255)),
        sa.Column(
            "depends_on_routine_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automation_routine.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "execution_mode",
            sa.String(32),
            nullable=False,
            server_default="human_review",
        ),
        sa.Column("merge_lock", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "requirements",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_automation_routine_org_enabled",
        "automation_routine",
        ["org_id", "enabled"],
    )
    op.create_index(
        "ix_automation_routine_repo_kind",
        "automation_routine",
        ["repo_id", "kind"],
    )

    op.create_table(
        "routine_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "routine_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automation_routine.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job.id", ondelete="SET NULL"),
        ),
        sa.Column("summary", sa.Text()),
        sa.Column(
            "details",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("routine_id", "scheduled_for", name="uq_routine_run_slot"),
    )
    op.create_index(
        "ix_routine_run_org_created", "routine_run", ["org_id", "created_at"]
    )
    op.create_index("ix_routine_run_routine_id", "routine_run", ["routine_id"])


def downgrade() -> None:
    op.drop_index("ix_routine_run_routine_id", table_name="routine_run")
    op.drop_index("ix_routine_run_org_created", table_name="routine_run")
    op.drop_table("routine_run")
    op.drop_index("ix_automation_routine_repo_kind", table_name="automation_routine")
    op.drop_index("ix_automation_routine_org_enabled", table_name="automation_routine")
    op.drop_table("automation_routine")
