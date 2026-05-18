"""Operational ORM tables for the operator console.

These tables back the Settings / Policies / Auto-repair / Audit-export
/ Auth surfaces. They were intentionally not part of the v1 schema in
`models.py` (which is the worker's canonical view of repos, jobs,
findings, repairs, audit, provenance, CI, external issues) and are
added as a strict superset by migration `0004_console_ops`.

This module is imported from `migrations/env.py` so Alembic autogenerate
sees the tables. Importing it from a repository module also registers
them at runtime; importing from `__init__.py` would cause a cycle
because `db.py` is what defines `Base`.
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
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from selfrepair.persistence.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _value_enum(enum_cls: type[StrEnum], *, name: str) -> SqlEnum:
    return SqlEnum(
        enum_cls,
        name=name,
        values_callable=lambda cls: [m.value for m in cls],
    )


# -------------------- Integrations --------------------


class IntegrationStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    ERROR = "error"
    PENDING = "pending"


class IntegrationConnection(Base):
    """Per-org provider credential pointer.

    `credential_ref` is an opaque pointer into the secret manager (KMS
    ARN, Vault path, env-var name, ...). The actual token is NEVER
    stored in Postgres; this row is just metadata + the pointer the
    worker resolves at execution time.
    """

    __tablename__ = "integration_connection"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[IntegrationStatus] = mapped_column(
        _value_enum(IntegrationStatus, name="integration_status"),
        default=IntegrationStatus.ACTIVE,
        nullable=False,
    )
    credential_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    __table_args__ = (
        UniqueConstraint(
            "org_id", "provider", "display_name",
            name="uq_integration_connection",
        ),
    )


# -------------------- API tokens / sessions --------------------


class ApiToken(Base):
    """Hashed API tokens for CLIs and service-to-service auth.

    Only `hash` and a non-secret `prefix` are stored. The plaintext
    token is shown to the user once at creation.
    """

    __tablename__ = "api_token"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_account.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class Session(Base):
    """Auth session row backing cookie-based sessions.

    `token_hash` is what the cookie's session id resolves to; it is
    looked up by the auth middleware on every request.
    """

    __tablename__ = "session"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text())


class UserInvitation(Base):
    __tablename__ = "user_invitation"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="viewer", nullable=False)
    inviter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL")
    )
    token_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    __table_args__ = (
        UniqueConstraint(
            "org_id", "email", name="uq_user_invitation_email"
        ),
    )


# -------------------- Schedules --------------------


class RepairSchedule(Base):
    """Persistent definition for the auto-repair surface.

    `repo_ids` and `policy` are JSON to avoid a cross-cutting join
    table for the v1 surface. When the policy bundle versioning lands
    `policy_id` becomes a real FK.
    """

    __tablename__ = "repair_schedule"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cron: Mapped[str] = mapped_column(String(64), nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(64), default="UTC", nullable=False
    )
    repo_ids: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    policy: Mapped[str | None] = mapped_column(String(255))
    trigger_label: Mapped[str | None] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_repair_schedule_org_enabled", "org_id", "enabled"),
    )


# -------------------- Snapshots / Artifacts --------------------


class RepoScanSnapshot(Base):
    """Time-series row per repo per scan; powers KPI sparklines."""

    __tablename__ = "repo_scan_snapshot"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repo.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    open_findings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    health_score: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        Index(
            "ix_repo_scan_snapshot_repo_ts",
            "repo_id",
            "snapshot_at",
        ),
    )


class ArtifactKind(StrEnum):
    LOG = "log"
    PATCH = "patch"
    SBOM = "sbom"
    PROVENANCE = "provenance"
    SARIF = "sarif"
    OTHER = "other"


class Artifact(Base):
    """Pointer row for a blob in object storage (S3 / GCS / MinIO).

    The bytes never live in Postgres; we keep a sha256 + size + URL so
    the SPA can fetch via a signed URL or tail via a streaming endpoint.
    """

    __tablename__ = "artifact"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job.id", ondelete="CASCADE")
    )
    repair_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repair.id", ondelete="CASCADE")
    )
    kind: Mapped[ArtifactKind] = mapped_column(
        _value_enum(ArtifactKind, name="artifact_kind"), nullable=False
    )
    storage_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_artifact_job", "job_id"),
        Index("ix_artifact_repair", "repair_id"),
    )


# -------------------- Notifications --------------------


class Notification(Base):
    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_account.id", ondelete="CASCADE"),
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(64))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_notification_user_unread", "user_id", "read_at"),
    )


# -------------------- Policy bundle versions --------------------


class PolicyBundleVersion(Base):
    """Versioned OPA bundle pointer.

    The bundle bytes live in object storage; this row keeps the
    deployable history so the operator can rollback.
    """

    __tablename__ = "policy_bundle_version"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    bundle_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    bundle_object_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    deployed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    __table_args__ = (
        UniqueConstraint(
            "org_id", "version", name="uq_policy_bundle_version_org_version"
        ),
    )
