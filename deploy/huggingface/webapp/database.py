"""Database models and session management for the SelfRepair webapp.

Prefers a configured Postgres ``DATABASE_URL`` (e.g. Neon) and gracefully falls
back to ephemeral SQLite on ``/tmp`` if the database is unreachable, so the
Space stays up even when outbound Postgres egress is blocked.
"""
from __future__ import annotations

import logging
import os as _os
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

logger = logging.getLogger(__name__)

_DB_DIR = _os.environ.get("SELFREPAIR_DB_DIR", "/tmp/selfrepair")
_SQLITE_URL = f"sqlite:///{_DB_DIR}/selfrepair.db"
DATABASE_URL = _os.environ.get("DATABASE_URL", _SQLITE_URL)


def _normalize(url: str) -> str:
    # SQLAlchemy needs an explicit driver for psycopg2.
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    return url


def _build_engine(url: str):
    if url.startswith("sqlite"):
        _os.makedirs(_DB_DIR, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    # Postgres: pre-ping + recycle for serverless/pooled backends like Neon.
    return create_engine(
        _normalize(url),
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 10},
    )


def _make_engine():
    """Use DATABASE_URL; fall back to SQLite if the DB can't be reached."""
    url = DATABASE_URL
    try:
        eng = _build_engine(url)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        if not url.startswith("sqlite"):
            logger.info("SelfRepair DB: connected to Postgres backend.")
        return eng
    except Exception as exc:  # pragma: no cover - depends on runtime egress
        if url.startswith("sqlite"):
            raise
        logger.warning(
            "SelfRepair DB: Postgres unreachable (%s); falling back to SQLite.",
            type(exc).__name__,
        )
        _os.makedirs(_DB_DIR, exist_ok=True)
        return _build_engine(_SQLITE_URL)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(32), primary_key=True, default=_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(200), nullable=True)
    role = Column(String(20), default="user")  # user | admin
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    # The single bootstrap superuser, created on first run. Protected: it can
    # never be demoted, deactivated, or deleted. It grants admin to others.
    is_root = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_utcnow)
    last_login = Column(DateTime, nullable=True)

    # Platform tokens (encrypted at rest in production)
    github_token = Column(Text, nullable=True)
    gitlab_token = Column(Text, nullable=True)
    hf_token = Column(Text, nullable=True)

    scans = relationship("ScanRun", back_populates="user", cascade="all, delete-orphan")


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id = Column(String(32), primary_key=True, default=_uuid)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime, default=_utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="running")  # running | completed | failed
    total_repos = Column(Integer, default=0)
    healthy = Column(Integer, default=0)
    degraded = Column(Integer, default=0)
    down = Column(Integer, default=0)
    repaired = Column(Integer, default=0)
    report_json = Column(Text, nullable=True)
    trigger = Column(String(50), default="manual")  # manual | scheduled

    user = relationship("User", back_populates="scans")
    reports = relationship("RepoReport", back_populates="scan", cascade="all, delete-orphan")


class RepoReport(Base):
    __tablename__ = "repo_reports"

    id = Column(String(32), primary_key=True, default=_uuid)
    scan_id = Column(String(32), ForeignKey("scan_runs.id"), nullable=False)
    repo_name = Column(String(300), nullable=False)
    platform = Column(String(20), default="github")
    kind = Column(String(20), default="code")
    status = Column(String(20), default="unknown")
    makefile_ok = Column(Boolean, default=False)
    pyproject_ok = Column(Boolean, default=False)
    health_test_ok = Column(Boolean, default=False)
    python311_ok = Column(Boolean, default=False)
    install_ok = Column(Boolean, default=False)
    test_ok = Column(Boolean, default=False)
    start_ok = Column(Boolean, default=False)
    fix_attempts = Column(Integer, default=0)
    changed_files = Column(Text, default="")
    notes = Column(Text, default="")
    pr_url = Column(String(500), nullable=True)
    duration_seconds = Column(Float, default=0.0)
    created_at = Column(DateTime, default=_utcnow)

    scan = relationship("ScanRun", back_populates="reports")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String(32), primary_key=True, default=_uuid)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class Connection(Base):
    """A configured connection to a SelfRepair service provider.

    provider is one of: ollabridge | gitpilot | matrixlab.
    The secret (OllaBridge ob_* key or service token) is stored
    Fernet-encrypted in ``api_key_enc`` — never in plaintext.
    """

    __tablename__ = "connections"

    id = Column(String(32), primary_key=True, default=_uuid)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String(40), nullable=False)
    base_url = Column(String(500), nullable=False, default="")
    api_key_enc = Column(Text, nullable=True)
    status = Column(String(20), default="unknown")  # unknown | ok | error
    detail = Column(Text, default="")
    last_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_provider"),)


class Message(Base):
    """An incoming maintenance/repair request from a client (machine or admin).

    Recorded as the system-of-record intake row. Deduplicated in code via
    ``idempotency_key`` (we index it rather than relying on a partial unique
    constraint, which SQLite cannot express for NULLs portably).
    """

    __tablename__ = "messages"

    id = Column(String(32), primary_key=True, default=_uuid)
    client_id = Column(String(200), nullable=False)
    requested_by = Column(String(200), nullable=True)
    type = Column(String(40), default="maintenance_request")  # maintenance_request | repair_plan
    repo_url = Column(String(500), nullable=False)
    branch = Column(String(200), default="main")
    mode = Column(String(40), default="dry_run")
    message = Column(Text, nullable=True)
    payload = Column(Text, nullable=True)  # JSON-encoded plan/extra
    idempotency_key = Column(String(200), nullable=True, index=True)
    status = Column(String(20), default="queued")  # queued | running | done | failed
    job_id = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class Job(Base):
    """A real repo health-check job produced from a Message."""

    __tablename__ = "jobs"

    id = Column(String(32), primary_key=True, default=_uuid)
    message_id = Column(String(32), nullable=True, index=True)
    repo_url = Column(String(500), nullable=False)
    branch = Column(String(200), default="main")
    status = Column(String(20), default="queued")  # queued | running | done | failed
    health_score = Column(Integer, nullable=True)
    report_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    finished_at = Column(DateTime, nullable=True)


class Notification(Base):
    """An operator-facing notification surfaced in the console bell/inbox."""

    __tablename__ = "notifications"

    id = Column(String(32), primary_key=True, default=_uuid)
    source = Column(String(200), default="system")  # client_id or "system"
    kind = Column(String(40), default="request_received")  # request_received | report_ready | action_needed
    title = Column(String(400), nullable=False)
    body = Column(Text, nullable=True)
    link = Column(String(200), nullable=True)  # job id
    read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_utcnow)


def _ensure_columns() -> None:
    """Lightweight in-place migration for columns added after first deploy."""
    insp_bind = engine
    try:
        from sqlalchemy import inspect as _inspect

        insp = _inspect(insp_bind)
        if "users" not in insp.get_table_names():
            return
        cols = {c["name"] for c in insp.get_columns("users")}
        bool_default = "0" if engine.dialect.name == "sqlite" else "false"
        for col in ("email_verified", "is_root"):
            if col not in cols:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE users ADD COLUMN {col} BOOLEAN "
                            f"NOT NULL DEFAULT {bool_default}"
                        )
                    )
                logger.info("SelfRepair DB: added users.%s column.", col)
    except Exception as exc:  # pragma: no cover
        logger.warning("SelfRepair DB: column check skipped (%s).", type(exc).__name__)


def init_db() -> None:
    """Create all tables and apply lightweight migrations."""
    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise
