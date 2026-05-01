"""Database models and session management for RepoGuardian Web UI."""
from __future__ import annotations

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
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

DATABASE_URL = "sqlite:////tmp/repoguardian/repoguardian.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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


def init_db() -> None:
    """Create all tables."""
    import os
    os.makedirs("/tmp/repoguardian", exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise
