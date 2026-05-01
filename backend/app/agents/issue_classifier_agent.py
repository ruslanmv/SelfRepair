from __future__ import annotations

from backend.app.schemas.issue import Issue
from selfrepair.models import RepoHealthReport, StandardCheck


class IssueClassifierAgent:
    """Classifies repository findings into actionable issues."""

    def run(self, report: RepoHealthReport) -> list[Issue]:
        issues: list[Issue] = []
        for check in report.checks:
            if check.ok:
                continue
            issues.append(self._issue_from_check(check))

        if report.install_result and not report.install_result.ok:
            issues.append(
                Issue(
                    title="Install step failed",
                    category="runtime",
                    severity="high",
                    description=_trim(report.install_result.stderr or report.install_result.stdout),
                    check_name="install",
                    recommendation="Review dependency files and installation command output.",
                )
            )
        if report.test_result and not report.test_result.ok:
            issues.append(
                Issue(
                    title="Test step failed",
                    category="quality",
                    severity="high",
                    description=_trim(report.test_result.stderr or report.test_result.stdout),
                    check_name="test",
                    recommendation="Fix failing tests or add a minimal health test when no tests exist.",
                )
            )
        if report.start_result and not report.start_result.ok:
            issues.append(
                Issue(
                    title="Start step failed",
                    category="runtime",
                    severity="medium",
                    description=_trim(report.start_result.stderr or report.start_result.stdout),
                    check_name="start",
                    recommendation="Confirm the start command and runtime entrypoint.",
                )
            )
        return issues

    @staticmethod
    def _issue_from_check(check: StandardCheck) -> Issue:
        mapping = {
            "makefile": ("Missing or incomplete Makefile", "delivery", "medium", "Add install, test, and start targets."),
            "pyproject": ("Missing pyproject.toml", "delivery", "medium", "Add Python packaging metadata."),
            "health_test": ("Missing health test", "quality", "high", "Add a minimal tests/test_health.py."),
            "python311": ("Python 3.11 compatibility not declared", "delivery", "medium", "Set requires-python to >=3.11,<3.13."),
            "uv": ("uv configuration missing", "delivery", "low", "Add [tool.uv] for modern Python workflows."),
            "readme": ("README missing", "documentation", "medium", "Add setup, usage, and validation instructions."),
        }
        title, category, severity, recommendation = mapping.get(
            check.name,
            (f"Failed check: {check.name}", "delivery", "medium", "Review repository standards."),
        )
        return Issue(
            title=title,
            category=category,  # type: ignore[arg-type]
            severity=severity,  # type: ignore[arg-type]
            description=check.details or recommendation,
            check_name=check.name,
            recommendation=recommendation,
        )


def _trim(value: str, limit: int = 800) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[:limit] + "..."
