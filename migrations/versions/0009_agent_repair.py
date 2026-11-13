"""agent repair: an intake for AI-agent issues sent by LangReplay

Revision ID: 0009_agent_repair
Revises: 0008_service_connections
Create Date: 2026-11-13

Additive. Two new tables; nothing existing changes. Plans, patches and static-check results are stored on the
row so a worker restart loses nothing. See docs/agent-repair.md.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_agent_repair"
down_revision: str | Sequence[str] | None = "0008_service_connections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "agent_repair",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default="langreplay"),
        sa.Column("attempt_id", sa.String(80), nullable=False),
        sa.Column("case_id", sa.String(200), nullable=False),
        sa.Column("evidence_id", sa.String(80), nullable=False),
        sa.Column("evidence", JSON, nullable=False),
        sa.Column("repo_url", sa.String(500), nullable=False),
        sa.Column("base_commit", sa.String(64), nullable=False),
        sa.Column("ref", sa.String(200), nullable=True),
        sa.Column("state", sa.String(32), nullable=False, server_default="planning"),
        sa.Column("plan", JSON, nullable=True),
        sa.Column("scope", JSON, nullable=True),
        sa.Column("patch", sa.Text(), nullable=True),
        sa.Column("patch_sha256", sa.String(80), nullable=True),
        sa.Column("changed_files", JSON, nullable=True),
        sa.Column("branch", sa.String(200), nullable=True),
        sa.Column("static_checks", JSON, nullable=True),
        sa.Column("coder", JSON, nullable=True),
        sa.Column("gitpilot_task_id", sa.String(128), nullable=True),
        sa.Column("pr_url", sa.String(500), nullable=True),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_by", sa.String(255), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("verification_run", sa.String(80), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "attempt_id", name="uq_agent_repair_org_attempt"),
    )
    op.create_index("ix_agent_repair_org_id", "agent_repair", ["org_id"])
    op.create_index("ix_agent_repair_state", "agent_repair", ["state"])
    op.create_table(
        "agent_repair_event",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("repair_id", sa.Uuid(), sa.ForeignKey("agent_repair.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("level", sa.String(16), nullable=False, server_default="info"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", JSON, nullable=True),
    )
    op.create_index("ix_agent_repair_event_repair_id", "agent_repair_event", ["repair_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_repair_event_repair_id", table_name="agent_repair_event")
    op.drop_table("agent_repair_event")
    op.drop_index("ix_agent_repair_state", table_name="agent_repair")
    op.drop_index("ix_agent_repair_org_id", table_name="agent_repair")
    op.drop_table("agent_repair")
