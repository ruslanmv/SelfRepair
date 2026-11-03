"""ORM models for code-review runs, findings, and publications.

Reviews are not repair jobs. A review never writes a `job` or `finding` row,
and a repair never satisfies a review check. Tenancy is `org_id` on every table.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from selfrepair.persistence.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ReviewRun(Base):
    """One review of one change set.

    Identity is `(org_id, repo_id, head_sha, base_sha, policy_version)`.
    Event kind is not part of the identity: a push and a pull-request
    synchronize for the same range share a run. Delivery id is stored for
    traceability and dedupe, not as the semantic key.
    """

    __tablename__ = "review_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repo.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    delivery_id: Mapped[str | None] = mapped_column(String(128))
    ref: Mapped[str | None] = mapped_column(String(512))
    pr_number: Mapped[int | None] = mapped_column(Integer)
    base_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    head_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    forced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    from_fork: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    engine: Mapped[str] = mapped_column(String(32), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(128))
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    conclusion: Mapped[str | None] = mapped_column(String(32))
    summary: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    sender_login: Mapped[str | None] = mapped_column(String(255))
    commit_shas: Mapped[list[str] | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "repo_id",
            "head_sha",
            "base_sha",
            "policy_version",
            name="uq_review_run_change_set",
        ),
        Index("ix_review_run_repo_ref", "repo_id", "ref"),
        Index("ix_review_run_delivery", "provider", "delivery_id"),
    )


class ReviewFinding(Base):
    """A single evidence-backed finding attached to one review run."""

    __tablename__ = "review_finding"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org.id", ondelete="CASCADE"), nullable=False, index=True
    )
    review_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("review_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    file_path: Mapped[str | None] = mapped_column(String(1024))
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)
    side: Mapped[str | None] = mapped_column(String(8))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)
    suggested_fix: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="deterministic")
    validation_state: Mapped[str] = mapped_column(String(32), nullable=False, default="accepted")
    resolution_state: Mapped[str] = mapped_column(String(32), nullable=False, default="open")

    __table_args__ = (
        UniqueConstraint("review_run_id", "fingerprint", name="uq_review_finding_fingerprint"),
        # Names match migration 0007 so autogenerate does not propose renames.
        Index("ix_review_finding_run", "review_run_id"),
        Index("ix_review_finding_severity", "review_run_id", "severity"),
    )


class ReviewPublication(Base):
    """One attempt to publish a run to a provider check or discussion."""

    __tablename__ = "review_publication"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org.id", ondelete="CASCADE"), nullable=False, index=True
    )
    review_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("review_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    fingerprints: Mapped[list[str] | None] = mapped_column(JSONB)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "review_run_id", "provider", "kind", name="uq_review_publication_target"
        ),
        Index("ix_review_publication_run", "review_run_id"),
    )


class ReviewDelivery(Base):
    """Durable webhook delivery claim. Redis is only a fast path."""

    __tablename__ = "review_delivery"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    delivery_id: Mapped[str] = mapped_column(String(128), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("provider", "delivery_id", name="uq_review_delivery"),
    )


class ReviewSettingsRow(Base):
    """Org-wide default (`repo_id` null) or a per-repository API override."""

    __tablename__ = "review_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repo.id", ondelete="CASCADE")
    )
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_review_settings_repo", "org_id", "repo_id"),
        # One org default and one override per repository (migration 0007).
        Index(
            "uq_review_settings_org_default",
            "org_id",
            unique=True,
            postgresql_where=text("repo_id IS NULL"),
        ),
        Index(
            "uq_review_settings_repo",
            "org_id",
            "repo_id",
            unique=True,
            postgresql_where=text("repo_id IS NOT NULL"),
        ),
    )
