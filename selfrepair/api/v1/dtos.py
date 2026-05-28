"""Stable client-contract DTOs (selfrepair/v1).

These DTOs implement the SelfRepair side of the contract defined by
matrix-maintainer in `agent-matrix/matrix-maintainer:docs/design/selfrepair-client-contract.md`.

They are intentionally a separate surface from `selfrepair.models` — the
internal models carry richer engine-specific fields; the v1 DTOs are the
stable wire shape exposed at `/v1/rpc` and via the in-process library API.

If you change a field here you are breaking the cross-repo contract.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "selfrepair/v1"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class _V1Base(BaseModel):
    """Common config for all v1 DTOs."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class RepoRefDTO(_V1Base):
    schema_version: str = SCHEMA_VERSION
    full_name: str
    clone_url: str
    default_branch: str = "main"
    platform: Literal["github", "gitlab", "huggingface"] = "github"
    private: bool = False


class HealthIssueDTO(_V1Base):
    schema_version: str = SCHEMA_VERSION
    repo: str
    issue_type: str
    details: str = ""
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RepoHealthReportDTO(_V1Base):
    schema_version: str = SCHEMA_VERSION
    repo: RepoRefDTO
    generated_at: str = Field(default_factory=_utc_now_iso)
    status: Literal["healthy", "degraded", "down", "unknown"] = "unknown"
    issues: list[HealthIssueDTO] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RepairResultDTO(_V1Base):
    schema_version: str = SCHEMA_VERSION
    repo: str
    applied: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    branch: str | None = None
    needs_escalation: bool = False
    escalation_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationReportDTO(_V1Base):
    schema_version: str = SCHEMA_VERSION
    repo: str
    install_ok: bool = False
    test_ok: bool = False
    start_ok: bool = False
    health_test_ok: bool = False
    sandbox: Literal["matrixlab", "local", "none"] = "none"
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class JsonReportDTO(_V1Base):
    schema_version: str = SCHEMA_VERSION
    repo: str
    generated_at: str = Field(default_factory=_utc_now_iso)
    health: RepoHealthReportDTO | None = None
    repair: RepairResultDTO | None = None
    validation: ValidationReportDTO | None = None
    audit: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "SCHEMA_VERSION",
    "HealthIssueDTO",
    "JsonReportDTO",
    "RepairResultDTO",
    "RepoHealthReportDTO",
    "RepoRefDTO",
    "ValidationReportDTO",
]
