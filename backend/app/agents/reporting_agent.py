from __future__ import annotations

from backend.app.schemas.final_report import FinalReport
from backend.app.schemas.issue import Issue
from backend.app.schemas.repair_patch import RepairPatch
from backend.app.schemas.validation_result import ValidationResult
from selfrepair.models import RepoHealthReport


class ReportingAgent:
    """Builds the final audit-ready repository repair report."""

    def run(
        self,
        report: RepoHealthReport,
        *,
        repo_url: str,
        branch: str,
        repair_mode: str,
        health_score_before: int,
        health_score_after: int,
        issues: list[Issue],
        repair_patches: list[RepairPatch],
        validation: ValidationResult,
    ) -> FinalReport:
        return FinalReport(
            repo=report.repo.full_name,
            repo_url=repo_url,
            branch=branch,
            repair_mode=repair_mode,
            health_score_before=health_score_before,
            health_score_after=health_score_after,
            issues_found=len(issues),
            fixes_applied=len(report.changed_files),
            validation_status=report.status,
            changed_files=report.changed_files,
            issues=issues,
            repair_patches=repair_patches,
            validation=validation,
            notes=report.notes,
        )
