"""ORM models for agent repairs (migration 0009_agent_repair).

Portable column types (Uuid, JSON with a JSONB variant) so the same models run on Postgres in production and on
SQLite in tests. Plans and patches are stored on the row, not in worker memory, so a restart loses nothing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from selfrepair.persistence.db import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")
EventId = BigInteger().with_variant(Integer(), "sqlite")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AgentRepair(Base):
    __tablename__ = "agent_repair"
    __table_args__ = (UniqueConstraint("org_id", "attempt_id", name="uq_agent_repair_org_attempt"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="langreplay")
    attempt_id: Mapped[str] = mapped_column(String(80), nullable=False)
    case_id: Mapped[str] = mapped_column(String(200), nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    repo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    base_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    ref: Mapped[str | None] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="planning", index=True)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    scope: Mapped[list[str] | None] = mapped_column(JsonType)
    patch: Mapped[str | None] = mapped_column(Text)
    patch_sha256: Mapped[str | None] = mapped_column(String(80))
    changed_files: Mapped[list[str] | None] = mapped_column(JsonType)
    branch: Mapped[str | None] = mapped_column(String(200))
    static_checks: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    coder: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    gitpilot_task_id: Mapped[str | None] = mapped_column(String(128))
    pr_url: Mapped[str | None] = mapped_column(String(500))
    pr_number: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_by: Mapped[str | None] = mapped_column(String(255))
    approved_by: Mapped[str | None] = mapped_column(String(255))
    verification_run: Mapped[str | None] = mapped_column(String(80))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class AgentRepairEvent(Base):
    __tablename__ = "agent_repair_event"

    id: Mapped[int] = mapped_column(EventId, primary_key=True, autoincrement=True)
    repair_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("agent_repair.id", ondelete="CASCADE"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
