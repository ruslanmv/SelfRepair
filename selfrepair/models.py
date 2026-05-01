from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


RepoPlatform = Literal["github", "huggingface", "gitlab"]
RepoKind = Literal["code", "model", "dataset", "space", "unknown"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class RepoRef(BaseModel):
    name: str
    full_name: str
    clone_url: str
    default_branch: str = "main"
    archived: bool = False
    private: bool = False
    platform: RepoPlatform = "github"
    kind: RepoKind = "code"
    namespace: str | None = None
    web_url: str | None = None


class StandardCheck(BaseModel):
    name: str
    ok: bool
    details: str = ""


class ExecutionResult(BaseModel):
    command: str
    return_code: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.return_code == 0


class RepairPlan(BaseModel):
    summary: str
    actions: list[str] = Field(default_factory=list)
    strategy: str = "local-template"


class SpaceDiagnosisResult(BaseModel):
    """Serializable summary of a Space diagnosis."""
    sdk: str = "unknown"
    app_file: str = ""
    hardware: str = "cpu-basic"
    runtime_stage: str = "unknown"
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    dead_patterns: list[str] = Field(default_factory=list)
    needs_gpu: bool = False
    needs_rebuild: bool = False
    severity: str = "info"
    fix_applied: bool = False
    fix_explanation: str = ""


class RepoHealthReport(BaseModel):
    repo: RepoRef
    generated_at: str = Field(default_factory=utc_now)
    branch_name: str | None = None
    status: str = "unknown"
    repo_type: str = "unknown"
    platform: RepoPlatform | None = None

    makefile_ok: bool = False
    pyproject_ok: bool = False
    health_test_ok: bool = False
    python311_ok: bool = False
    uv_ok: bool = False
    install_ok: bool = False
    test_ok: bool = False
    start_ok: bool = False
    metadata_ok: bool = False

    fix_attempts: int = 0
    changed_files: list[str] = Field(default_factory=list)
    checks: list[StandardCheck] = Field(default_factory=list)
    install_result: ExecutionResult | None = None
    test_result: ExecutionResult | None = None
    start_result: ExecutionResult | None = None
    repair_plan: RepairPlan | None = None
    pr_url: str | None = None
    pushed_branch: str | None = None
    notes: list[str] = Field(default_factory=list)

    # HuggingFace Space-specific
    space_diagnosis: SpaceDiagnosisResult | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.platform is None:
            self.platform = self.repo.platform

    def finalize_status(self) -> None:
        # Space-specific status
        if self.space_diagnosis:
            if self.space_diagnosis.fix_applied:
                self.status = "repaired"
            elif self.space_diagnosis.severity == "critical":
                self.status = "down"
            elif self.space_diagnosis.severity == "warning":
                self.status = "degraded"
            elif self.space_diagnosis.severity == "info" and not self.space_diagnosis.issues:
                self.status = "healthy"
            else:
                self.status = "unknown"
            return
        # Standard status
        if self.install_ok and self.test_ok and self.start_ok and self.health_test_ok:
            self.status = "healthy"
        elif any([self.install_ok, self.test_ok, self.start_ok, self.metadata_ok]):
            self.status = "degraded"
        elif self.notes:
            self.status = "down"
        else:
            self.status = "unknown"


class SiteSummary(BaseModel):
    title: str
    description: str
    generated_at: str = Field(default_factory=utc_now)
    healthy: int = 0
    degraded: int = 0
    down: int = 0
    unknown: int = 0


class Incident(BaseModel):
    title: str
    status: str
    timestamp: str = Field(default_factory=utc_now)
    details: str = ""


class InfraStatus(BaseModel):
    name: str
    status: str
    details: str = ""


class RepoRunContext(BaseModel):
    repo: RepoRef
    repo_dir: Path
    branch_name: str
    metadata: dict[str, Any] = Field(default_factory=dict)
