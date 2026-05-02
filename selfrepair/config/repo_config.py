"""Per-repository config (`.selfrepair.yml`).

The config is the contract between platform team and the tool. Defaults are
deliberately conservative (no LLM, no auto-merge, codeowners required) so a
repo without the file is opted out of risky behavior (ADR-0001).

CI Guardian additions are also conservative: tracing on by default,
auto-rerun and auto-repair OFF until the repo opts in.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

SeverityLiteral = Literal["info", "low", "medium", "high", "critical"]

_SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def _severity_le(a: str, b: str) -> bool:
    return _SEVERITY_RANK.get(a, 99) <= _SEVERITY_RANK.get(b, 99)


class AutoMergeRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    severity: SeverityLiteral = "low"
    require_ci_green: bool = True


class EscalateRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    max_iterations: int = Field(default=3, ge=1, le=10)


class Notifications(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slack: str | None = None
    email: list[str] = Field(default_factory=list)


class Budget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monthly_usd: float = Field(default=0.0, ge=0.0)


# -------------------- CI Guardian config --------------------


class CIAutoRerun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_attempts_per_failure: int = Field(default=1, ge=0, le=10)
    max_per_repo_per_hour: int = Field(default=5, ge=0, le=100)
    classes: list[str] = Field(default_factory=list)


class CIAutoRepair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    require_approval: bool = True
    max_per_repo_per_day: int = Field(default=1, ge=0, le=20)
    classes: list[str] = Field(default_factory=list)


class CISafety(BaseModel):
    model_config = ConfigDict(extra="forbid")

    never_repair_classes: list[str] = Field(
        default_factory=lambda: [
            "secret_or_env_missing",
            "permission_error",
            "security_scan_failure",
        ]
    )
    redact_logs: bool = True
    max_log_excerpt_chars: int = Field(default=12000, ge=1000, le=50000)


class CIGuardianConfig(BaseModel):
    """Per-repo CI Guardian section in `.selfrepair.yml`."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    trace_workflows: bool = True
    scheduled_verification: bool = True
    verification_interval_minutes: int = Field(default=15, ge=1, le=1440)
    auto_rerun: CIAutoRerun = Field(default_factory=CIAutoRerun)
    auto_repair: CIAutoRepair = Field(default_factory=CIAutoRepair)
    safety: CISafety = Field(default_factory=CISafety)


class RepoConfig(BaseModel):
    """Resolved config for a single repository.

    Loaded from `.selfrepair.yml` at the repo root, merged over org defaults.
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    extends: str | None = None
    schedule: str = "weekly"
    auto_merge: list[AutoMergeRule] = Field(default_factory=list)
    escalate_to_llm: list[EscalateRule] = Field(default_factory=list)
    deny_paths: list[str] = Field(
        default_factory=lambda: ["migrations/**", "infra/prod/**"]
    )
    codeowners_required: bool = True
    budget: Budget = Field(default_factory=Budget)
    notifications: Notifications = Field(default_factory=Notifications)
    ci_guardian: CIGuardianConfig = Field(default_factory=CIGuardianConfig)

    @field_validator("deny_paths")
    @classmethod
    def _no_negation(cls, value: list[str]) -> list[str]:
        for pattern in value:
            if pattern.startswith("!"):
                raise ValueError(
                    "deny_paths does not support negation patterns; "
                    "use a positive allow-list at the org level instead"
                )
        return value

    def llm_enabled_for(self, kind: str) -> bool:
        return any(rule.kind == kind for rule in self.escalate_to_llm)

    def llm_iterations_for(self, kind: str) -> int:
        for rule in self.escalate_to_llm:
            if rule.kind == kind:
                return rule.max_iterations
        return 0

    def auto_merge_for(self, kind: str, severity: str) -> AutoMergeRule | None:
        for rule in self.auto_merge:
            if rule.kind == kind and _severity_le(severity, rule.severity):
                return rule
        return None


def load_repo_config(workspace: Path) -> RepoConfig:
    """Load `.selfrepair.yml` from a workspace, returning safe defaults if absent."""
    config_path = workspace / ".selfrepair.yml"
    if not config_path.is_file():
        return RepoConfig()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return RepoConfig.model_validate(raw)
