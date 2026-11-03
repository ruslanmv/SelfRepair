"""reviewer: review runs, findings, publications, settings

Revision ID: 0007_reviewer
Revises: 0006_routines
Create Date: 2026-11-02

Strictly additive. Adds the code-review tables and a nullable installation id
on `repo`. It does not alter repair jobs, findings, or the repair state machine.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_reviewer"
down_revision: Union[str, Sequence[str], None] = "0006_routines"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "repo",
        sa.Column("github_installation_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_repo_github_installation", "repo", ["github_installation_id"]
    )

    op.create_table(
        "review_run",
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
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("delivery_id", sa.String(128)),
        sa.Column("ref", sa.String(512)),
        sa.Column("pr_number", sa.Integer()),
        sa.Column("base_sha", sa.String(64), nullable=False),
        sa.Column("head_sha", sa.String(64), nullable=False),
        sa.Column("forced", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("from_fork", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("engine", sa.String(32), nullable=False),
        sa.Column("model_id", sa.String(128)),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("conclusion", sa.String(32)),
        sa.Column("summary", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("sender_login", sa.String(255)),
        sa.Column("commit_shas", postgresql.JSONB()),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "org_id",
            "repo_id",
            "head_sha",
            "base_sha",
            "policy_version",
            name="uq_review_run_change_set",
        ),
    )
    op.create_index("ix_review_run_org_id", "review_run", ["org_id"])
    op.create_index("ix_review_run_repo_id", "review_run", ["repo_id"])
    op.create_index("ix_review_run_repo_ref", "review_run", ["repo_id", "ref"])
    op.create_index("ix_review_run_delivery", "review_run", ["provider", "delivery_id"])

    op.create_table(
        "review_finding",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "review_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("review_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("file_path", sa.String(1024)),
        sa.Column("start_line", sa.Integer()),
        sa.Column("end_line", sa.Integer()),
        sa.Column("side", sa.String(8)),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text()),
        sa.Column("suggested_fix", sa.Text()),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("validation_state", sa.String(32), nullable=False),
        sa.Column("resolution_state", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "review_run_id", "fingerprint", name="uq_review_finding_fingerprint"
        ),
    )
    op.create_index("ix_review_finding_org_id", "review_finding", ["org_id"])
    op.create_index("ix_review_finding_run", "review_finding", ["review_run_id"])
    op.create_index(
        "ix_review_finding_severity", "review_finding", ["review_run_id", "severity"]
    )

    op.create_table(
        "review_publication",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "review_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("review_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("fingerprints", postgresql.JSONB()),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "review_run_id", "provider", "kind", name="uq_review_publication_target"
        ),
    )
    op.create_index("ix_review_publication_org_id", "review_publication", ["org_id"])
    op.create_index(
        "ix_review_publication_run", "review_publication", ["review_run_id"]
    )

    op.create_table(
        "review_delivery",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("delivery_id", sa.String(128), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "delivery_id", name="uq_review_delivery"),
    )

    op.create_table(
        "review_settings",
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
            nullable=True,
        ),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_review_settings_org_id", "review_settings", ["org_id"])
    op.create_index(
        "ix_review_settings_repo", "review_settings", ["org_id", "repo_id"]
    )
    op.create_index(
        "uq_review_settings_org_default",
        "review_settings",
        ["org_id"],
        unique=True,
        postgresql_where=sa.text("repo_id IS NULL"),
    )
    op.create_index(
        "uq_review_settings_repo",
        "review_settings",
        ["org_id", "repo_id"],
        unique=True,
        postgresql_where=sa.text("repo_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_review_settings_repo", table_name="review_settings")
    op.drop_index("uq_review_settings_org_default", table_name="review_settings")
    op.drop_index("ix_review_settings_repo", table_name="review_settings")
    op.drop_index("ix_review_settings_org_id", table_name="review_settings")
    op.drop_table("review_settings")
    op.drop_table("review_delivery")
    op.drop_index("ix_review_publication_run", table_name="review_publication")
    op.drop_index("ix_review_publication_org_id", table_name="review_publication")
    op.drop_table("review_publication")
    op.drop_index("ix_review_finding_severity", table_name="review_finding")
    op.drop_index("ix_review_finding_run", table_name="review_finding")
    op.drop_index("ix_review_finding_org_id", table_name="review_finding")
    op.drop_table("review_finding")
    op.drop_index("ix_review_run_delivery", table_name="review_run")
    op.drop_index("ix_review_run_repo_ref", table_name="review_run")
    op.drop_index("ix_review_run_repo_id", table_name="review_run")
    op.drop_index("ix_review_run_org_id", table_name="review_run")
    op.drop_table("review_run")
    op.drop_index("ix_repo_github_installation", table_name="repo")
    op.drop_column("repo", "github_installation_id")
