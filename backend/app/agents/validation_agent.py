from __future__ import annotations

from backend.app.schemas.validation_result import ValidationResult
from selfrepair.models import RepoHealthReport


class ValidationAgent:
    """Converts engine verification results into an API validation object."""

    def run(self, report: RepoHealthReport) -> ValidationResult:
        return ValidationResult(
            validation_status=report.status,
            install_passed=report.install_ok,
            tests_passed=report.test_ok,
            start_passed=report.start_ok,
            health_test_passed=report.health_test_ok,
            notes=report.notes,
        )
