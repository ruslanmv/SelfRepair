"""console_ops: integrations, sessions, schedules, snapshots, artifacts,
notifications, policy bundles, user invitations + perf indexes.

Revision ID: 0004_console_ops
Revises: 0003_external_issues
Create Date: 2026-05-08

Strictly additive. Adds the operational tables the operator console
needs (Settings, Auto-repair, Audit, Policies, Notifications) and the
perf indexes that keep the dashboard / list endpoints cheap as the
dataset grows.

No existing tables are touched. The downgrade drops everything in
reverse-creation order; enums are dropped after their tables.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_console_ops"
down_revision: Union[str, Sequence[str], None] = "0003_external_issues"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    integration_status = sa.Enum(
        "active", "revoked", "error", "pending",
        name="integration_status",
    )
    artifact_kind = sa.Enum(
        "log", "patch", "sbom", "provenance", "sarif", "other",
        name="artifact_kind",
    )

    # ---- integration_connection ----
    op.create_table(
        "integration_connection",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("account", sa.String(255)),
        sa.Column(
            "status", integration_status,
            nullable=False, server_default="active",
        ),
        sa.Column("credential_ref", sa.String(512), nullable=False),
        sa.Column("config", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "org_id", "provider", "display_name",
            name="uq_integration_connection",
        ),
    )
    op.create_index(
        "ix_integration_connection_org", "integration_connection", ["org_id"]
    )

    # ---- api_token ----
    op.create_table(
        "api_token",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.id", ondelete="CASCADE"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("hash", sa.String(128), nullable=False, unique=True),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("scopes", postgresql.JSONB(), server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_api_token_org", "api_token", ["org_id"])

    # ---- session ----
    op.create_table(
        "session",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.Text()),
    )
    op.create_index("ix_session_org", "session", ["org_id"])
    op.create_index("ix_session_user", "session", ["user_id"])

    # ---- user_invitation ----
    op.create_table(
        "user_invitation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column(
            "role", sa.String(32),
            nullable=False, server_default="viewer",
        ),
        sa.Column(
            "inviter_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.id", ondelete="SET NULL"),
        ),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "org_id", "email", name="uq_user_invitation_email"
        ),
    )
    op.create_index("ix_user_invitation_org", "user_invitation", ["org_id"])

    # ---- repair_schedule ----
    op.create_table(
        "repair_schedule",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("cron", sa.String(64), nullable=False),
        sa.Column(
            "timezone", sa.String(64),
            nullable=False, server_default="UTC",
        ),
        sa.Column("repo_ids", postgresql.JSONB(), server_default="[]"),
        sa.Column("policy", sa.String(255)),
        sa.Column("trigger_label", sa.String(64)),
        sa.Column(
            "enabled", sa.Boolean(),
            nullable=False, server_default=sa.text("true"),
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_repair_schedule_org", "repair_schedule", ["org_id"])
    op.create_index(
        "ix_repair_schedule_org_enabled",
        "repair_schedule", ["org_id", "enabled"],
    )

    # ---- repo_scan_snapshot ----
    op.create_table(
        "repo_scan_snapshot",
        sa.Column(
            "id", sa.BigInteger(), primary_key=True, autoincrement=True
        ),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "repo_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repo.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "open_findings", sa.Integer(),
            nullable=False, server_default="0",
        ),
        sa.Column(
            "health_score", sa.Integer(),
            nullable=False, server_default="100",
        ),
        sa.Column("metrics", postgresql.JSONB()),
    )
    op.create_index(
        "ix_repo_scan_snapshot_org", "repo_scan_snapshot", ["org_id"]
    )
    op.create_index(
        "ix_repo_scan_snapshot_repo_ts",
        "repo_scan_snapshot", ["repo_id", "snapshot_at"],
    )

    # ---- artifact ----
    op.create_table(
        "artifact",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "job_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "repair_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repair.id", ondelete="CASCADE"),
        ),
        sa.Column("kind", artifact_kind, nullable=False),
        sa.Column("storage_url", sa.String(1024), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column(
            "size_bytes", sa.BigInteger(),
            nullable=False, server_default="0",
        ),
        sa.Column("media_type", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_artifact_org", "artifact", ["org_id"])
    op.create_index("ix_artifact_job", "artifact", ["job_id"])
    op.create_index("ix_artifact_repair", "artifact", ["repair_id"])

    # ---- notification ----
    op.create_table(
        "notification",
        sa.Column(
            "id", sa.BigInteger(), primary_key=True, autoincrement=True
        ),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.id", ondelete="CASCADE"),
        ),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("target_type", sa.String(64)),
        sa.Column("target_id", sa.String(64)),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notification_org", "notification", ["org_id"])
    op.create_index("ix_notification_created_at", "notification", ["created_at"])
    op.create_index(
        "ix_notification_user_unread",
        "notification", ["user_id", "read_at"],
    )

    # ---- policy_bundle_version ----
    op.create_table(
        "policy_bundle_version",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("bundle_sha", sa.String(64), nullable=False),
        sa.Column("bundle_object_url", sa.String(1024), nullable=False),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deployed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "org_id", "version", name="uq_policy_bundle_version_org_version"
        ),
    )
    op.create_index(
        "ix_policy_bundle_version_org",
        "policy_bundle_version", ["org_id"],
    )

    # ---- additive perf indexes on existing tables ----
    # job (org_id, repo_id, state, started_at DESC) accelerates the
    # console's job list. Create with IF NOT EXISTS so reruns are safe
    # if a deployment hot-patched a duplicate index manually.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_job_console_list "
        "ON job (org_id, started_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_repair_created_desc "
        "ON repair (created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_log_org_id_desc "
        "ON audit_log (org_id, id DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_finding_console_list "
        "ON finding (org_id, last_seen_at DESC, id DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_finding_console_list")
    op.execute("DROP INDEX IF EXISTS ix_audit_log_org_id_desc")
    op.execute("DROP INDEX IF EXISTS ix_repair_created_desc")
    op.execute("DROP INDEX IF EXISTS ix_job_console_list")

    op.drop_table("policy_bundle_version")
    op.drop_table("notification")
    op.drop_table("artifact")
    op.drop_table("repo_scan_snapshot")
    op.drop_table("repair_schedule")
    op.drop_table("user_invitation")
    op.drop_table("session")
    op.drop_table("api_token")
    op.drop_table("integration_connection")
    op.execute("DROP TYPE IF EXISTS artifact_kind")
    op.execute("DROP TYPE IF EXISTS integration_status")
