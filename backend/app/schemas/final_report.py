from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.schemas.issue import Issue
from backend.app.schemas.repair_patch import RepairPatch
from backend.app.schemas.validation_result import ValidationResult


class FinalReport(BaseModel):
    repo: str
    repo_url: str
    branch: str
    repair_mode: str
    health_score_before: int
    health_score_after: int
    issues_found: int
    fixes_applied: int
    validation_status: str
    changed_files: list[str] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    repair_patches: list[RepairPatch] = Field(default_factory=list)
    validation: ValidationResult | None = None
    notes: list[str] = Field(default_factory=list)
